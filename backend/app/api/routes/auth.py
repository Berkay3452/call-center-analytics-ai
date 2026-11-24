"""Servis anahtarı (`X-Service-Key`), tekne sahibi kimliği (`X-User-Id`) ve kullanıcı girişi."""

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import OwnerIdDep, ServiceCallerDep, SessionDep, SettingsDep
from app.core.errors import ConflictError, TooManyRequestsError, UnauthorizedError
from app.core.middleware import client_ip_var
from app.core.security import ServiceCaller
from app.db.models.external import Customer
from app.domain.accounts import AccountRole
from app.domain.audit import AuditAction, AuditActorRole, AuditOutcome
from app.schemas.api import LoginIn, LoginOut, RegisterIn
from app.schemas.common import ErrorResponse
from app.services.accounts import (
    EmailTakenError,
    LoginFailure,
    PasswordPolicyError,
    enforce_login_ip_limit,
    record_login_failure_ip,
    register_owner,
    verify_credentials,
)
from app.services.audit import record_audit_event_isolated

router = APIRouter(tags=["auth"])

GENERIC_LOGIN_ERROR = "Kullanıcı adı veya parola hatalı."


@router.get(
    "/me",
    response_model=ServiceCaller,
    responses={401: {"model": ErrorResponse}},
)
async def me(caller: ServiceCallerDep) -> ServiceCaller:
    """Servis anahtarını doğrular; varsa `X-User-Id` başlığını döndürür (admin için opsiyonel)."""
    return caller


@router.get(
    "/me/owner",
    response_model=ServiceCaller,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def me_owner(owner_id: OwnerIdDep) -> ServiceCaller:
    """Tekne sahibi uçları için servis anahtarını ve zorunlu `X-User-Id` başlığını doğrular."""
    return ServiceCaller(authenticated=True, owner_id=owner_id)


@router.post(
    "/auth/login",
    response_model=LoginOut,
    operation_id="login",
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def login(
    body: LoginIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _caller: ServiceCallerDep,
) -> LoginOut:
    """Kullanıcı girişi (#369): seçilen rolün hesap tablosunda kullanıcı adı + parola doğrulanır.

    Yalnızca servis anahtarıyla çağrılır (çağıran Next sunucusudur, tarayıcı değil). Her
    başarısızlık (kullanıcı yok, parola yanlış, pasif, kilitli, yanlış rol) AYNI 401 iletisini
    döner; hesabın var olup olmadığı belli edilmez. Başarısız denemeler hesap sayacına ve IP
    bütçesine yazılır; bütçe dolunca 429.
    """
    limiter = getattr(request.app.state, "rate_limiter", None)
    ip = client_ip_var.get() or "bilinmeyen"
    window, limit = settings.rate_limit_window_s, settings.rate_limit_auth_fail_per_min
    await enforce_login_ip_limit(limiter, ip, limit=limit, window_s=window)

    role = AccountRole(body.role)
    result = await verify_credentials(session, role, body.username, body.password)
    await session.commit()  # başarısız deneme sayacı ve kilit kalıcı olsun

    factory = request.app.state.session_factory
    if not result.ok:
        await record_login_failure_ip(limiter, ip, limit=limit, window_s=window)
        neden = result.failure.value if result.failure else LoginFailure.UNKNOWN_USER.value
        await record_audit_event_isolated(
            factory,
            action=AuditAction.HESAP_KILITLENDI
            if result.just_locked
            else AuditAction.GIRIS_BASARISIZ,
            actor_role=AuditActorRole.ANONIM,
            target_type=f"hesap_{role.value}",
            target_id=result.account_id,
            outcome=AuditOutcome.REDDEDILDI,
            details={"rol": role.value, "neden": neden},
        )
        raise UnauthorizedError(GENERIC_LOGIN_ERROR)

    assert result.account_id is not None and result.role is not None
    display_name = result.display_name or ""
    if result.customer_id is not None:
        name = await session.scalar(
            select(Customer.full_name).where(Customer.id == result.customer_id)
        )
        display_name = name or ""
    await record_audit_event_isolated(
        factory,
        action=AuditAction.GIRIS_BASARILI,
        actor_id=result.account_id,
        actor_role=(
            AuditActorRole.TEKNE_SAHIBI if role is AccountRole.OWNER else AuditActorRole.SERVIS
        ),
        target_type=f"hesap_{role.value}",
        target_id=result.account_id,
        details={"rol": role.value},
    )
    return LoginOut(
        role=body.role,
        account_id=result.account_id,
        customer_id=result.customer_id,
        display_name=display_name,
    )


REGISTER_PER_HOUR = 10  # IP başına kayıt denemesi (toplu hesap açmayı engeller)
REGISTER_ERROR = "Bu bilgilerle kayıt yapılamadı. Giriş yapmayı deneyin."


@router.post(
    "/auth/register",
    response_model=LoginOut,
    status_code=201,
    operation_id="register",
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def register(
    body: RegisterIn,
    request: Request,
    session: SessionDep,
    _caller: ServiceCallerDep,
) -> LoginOut:
    """Kaydol (#382): müşteri + tekne sahibi hesabı oluşturur ve girişe hazır `LoginOut` döner.

    Yalnızca `owner` hesabı açılır; yönetici hesabı bu uçtan açılamaz. E-posta kayıtlıysa genel 409.
    IP başına saatte `REGISTER_PER_HOUR` deneme. Parola yalnızca argon2id karması olarak saklanır.
    """
    limiter = getattr(request.app.state, "rate_limiter", None)
    ip = client_ip_var.get() or "bilinmeyen"
    if limiter is not None:
        decision = await limiter.hit(f"kayit:{ip}", REGISTER_PER_HOUR, 3600)
        if not decision.allowed:
            raise TooManyRequestsError(
                "Çok fazla kayıt denemesi; lütfen daha sonra tekrar deneyin.",
                retry_after_s=decision.retry_after_s,
            )
    try:
        account, customer = await register_owner(
            session,
            full_name=f"{body.first_name} {body.last_name}",
            phone=body.phone,
            email=body.email,
            password=body.password,
        )
    except EmailTakenError:
        await session.rollback()
        raise ConflictError(REGISTER_ERROR) from None
    except PasswordPolicyError as exc:
        await session.rollback()
        raise ConflictError(str(exc)) from None
    await session.commit()
    await record_audit_event_isolated(
        request.app.state.session_factory,
        action=AuditAction.HESAP_OLUSTURULDU,
        actor_id=account.id,
        actor_role=AuditActorRole.TEKNE_SAHIBI,
        target_type="hesap_owner",
        target_id=account.id,
        details={"rol": "owner"},
    )
    return LoginOut(
        role="owner",
        account_id=account.id,
        customer_id=customer.id,
        display_name=customer.full_name,
    )

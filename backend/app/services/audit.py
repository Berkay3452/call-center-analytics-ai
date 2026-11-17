"""Denetim günlüğü servisi (#267): tek giriş noktası `record_audit_event`.

Kullanım (iş akışının işlemine eklenir; `commit` çağıran tarafındır, böylece olay iş ile birlikte
kalıcı olur veya iş geri alınırsa olay da gitmez):

    await record_audit_event(
        session,
        action=AuditAction.CRM_ONAYLANDI,
        actor=caller,                       # ServiceCaller (isteğe bağlı)
        target_type="call", target_id=call_id,
        details={"duzenlendi": True},
    )

İşlemin geri alınacağı durumlarda (ör. kimlik doğrulama başarısızlığı, reddedilen istek) kendi
oturumunda yazan `record_audit_event_isolated` kullanılır.

Kişisel veri yazılmaz. Bu fonksiyon girdiyi doğrular ve kural dışı değeri `AuditDataError` ile
reddeder:
- `target_id` ve `details` metin değerleri yalnızca `[A-Za-z0-9_.:-]` (en çok 64 karakter)
  içerebilir: kimlik, tür veya sabit değer; boşluk, `@`, `+` ve serbest metin geçmez.
- 9 ve daha çok haneli yalnız rakam (telefon, T.C. kimlik no, kart no gibi) reddedilir.
- `details` en çok 10 anahtar taşır; değerler yalnızca metin, sayı, bool veya `None` olur.
- `request_id` ve `ip` bağlamdan (istek ara katmanı) otomatik doldurulur; IP biçimi doğrulanır.
"""

import asyncio
import ipaddress
import re
import uuid
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.middleware import client_ip_var
from app.core.security import ServiceCaller
from app.db.models.audit import AuditLog
from app.domain.audit import AuditAction, AuditActorRole, AuditOutcome

log = structlog.get_logger(__name__)

_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_LONG_DIGITS = re.compile(r"^\d{9,}$")
MAX_DETAIL_KEYS = 10
ISOLATED_TIMEOUT_S = 3.0

DetailValue = str | int | float | bool | None


class AuditDataError(ValueError):
    """Denetim kaydına yazılmaması gereken (kişisel veri riski taşıyan) değer verildi."""


def _safe_token(value: object, what: str) -> str:
    text = str(value)
    if not _TOKEN.fullmatch(text) or _LONG_DIGITS.fullmatch(text):
        raise AuditDataError(f"{what}: yalnızca kimlik/tür değeri yazılabilir.")
    return text


def sanitize_details(details: Mapping[str, Any] | None) -> dict[str, DetailValue]:
    """`details` sözlüğünü doğrular; kural dışı anahtar veya değerde `AuditDataError`."""
    if not details:
        return {}
    if len(details) > MAX_DETAIL_KEYS:
        raise AuditDataError(f"details en çok {MAX_DETAIL_KEYS} anahtar taşıyabilir.")
    clean: dict[str, DetailValue] = {}
    for key, value in details.items():
        if not _KEY.fullmatch(key):
            raise AuditDataError(f"details anahtarı geçersiz: {key!r}")
        if value is None or isinstance(value, bool | int | float):
            clean[key] = value
        elif isinstance(value, uuid.UUID | str):
            clean[key] = _safe_token(value, f"details.{key}")
        else:
            raise AuditDataError(f"details.{key}: desteklenmeyen tür {type(value).__name__}.")
    return clean


def _coerce_actor_id(actor_id: object) -> uuid.UUID | None:
    if actor_id is None or actor_id == "":
        return None
    if isinstance(actor_id, uuid.UUID):
        return actor_id
    try:
        return uuid.UUID(str(actor_id))
    except ValueError:
        raise AuditDataError("actor_id UUID olmalıdır.") from None


def _valid_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def actor_of(caller: ServiceCaller | None) -> tuple[uuid.UUID | None, AuditActorRole]:
    """Servis çağrısından (kimlik, rol) çifti. Hesap sistemi (#278) gelince burası genişler."""
    if caller is None:
        return None, AuditActorRole.SISTEM
    if caller.owner_id:
        role = getattr(caller, "role", None)
        if role is not None and role != "owner":
            # Kimlikli yönetici kullanıcı (#275): kimliği kaydedilir, rolü tekne sahibi değildir.
            return uuid.UUID(caller.owner_id), AuditActorRole.SERVIS
        return uuid.UUID(caller.owner_id), AuditActorRole.TEKNE_SAHIBI
    return None, AuditActorRole.SERVIS


def build_audit_event(
    *,
    action: AuditAction,
    actor: ServiceCaller | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_role: AuditActorRole | str | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    outcome: AuditOutcome = AuditOutcome.BASARILI,
    details: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Doğrulanmış `AuditLog` satırı üretir (oturuma eklemez)."""
    derived_id, derived_role = actor_of(actor) if actor is not None else (None, None)
    ctx = structlog.contextvars.get_contextvars()
    role = actor_role or derived_role
    rid = request_id or ctx.get("request_id")
    return AuditLog(
        actor_id=_coerce_actor_id(actor_id) or derived_id,
        actor_role=AuditActorRole(role).value if role else None,
        action=AuditAction(action).value,
        target_type=_safe_token(target_type, "target_type") if target_type else None,
        target_id=_safe_token(target_id, "target_id") if target_id is not None else None,
        outcome=AuditOutcome(outcome).value,
        # İstemci başlığından gelebildiği için kural dışıysa hata değil, boş bırakılır.
        request_id=str(rid) if rid and _TOKEN.fullmatch(str(rid)) else None,
        ip=_valid_ip(ip or client_ip_var.get()),
        details=sanitize_details(details),
    )


async def record_audit_event(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor: ServiceCaller | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_role: AuditActorRole | str | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    outcome: AuditOutcome = AuditOutcome.BASARILI,
    details: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Olayı çağıranın işlemine ekler (flush eder, commit ETMEZ). Bkz. modül açıklaması."""
    event = build_audit_event(
        action=action,
        actor=actor,
        actor_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
        details=details,
        request_id=request_id,
        ip=ip,
    )
    db.add(event)
    await db.flush()
    return event


async def has_recent_audit_event(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor: ServiceCaller | None,
    target_type: str,
    target_id: object,
    within_s: int,
) -> bool:
    """Aynı eylem, hedef, eylemi yapan ve IP için son `within_s` saniyede kayıt var mı?

    Çok sayıda istek atan akışlarda (ses oynatıcının Range istekleri) her isteği değil, her
    pencerede en az bir kaydı garanti etmek için kullanılır.
    """
    actor_id, role = actor_of(actor)
    ip = _valid_ip(client_ip_var.get())
    stmt = (
        select(AuditLog.id)
        .where(
            AuditLog.action == AuditAction(action).value,
            AuditLog.target_type == target_type,
            AuditLog.target_id == _safe_token(target_id, "target_id"),
            AuditLog.actor_role == role.value,
            AuditLog.occurred_at >= func.now() - timedelta(seconds=within_s),
            AuditLog.actor_id.is_(None) if actor_id is None else AuditLog.actor_id == actor_id,
            AuditLog.ip.is_(None) if ip is None else AuditLog.ip == ip,
        )
        .limit(1)
    )
    return (await db.scalar(stmt)) is not None


async def record_audit_event_isolated(
    session_factory: async_sessionmaker[AsyncSession], **kwargs: Any
) -> bool:
    """Olayı kendi oturum ve işleminde yazar (iş geri alınsa da kalır).

    Hata (veritabanı kapalı, zaman aşımı) isteği bozmasın diye yutulur ve `False` döner;
    doğrulama hatası (`AuditDataError`) yine fırlatılır, çünkü kod hatasıdır.
    """
    event = build_audit_event(**kwargs)
    try:
        async with asyncio.timeout(ISOLATED_TIMEOUT_S):
            async with session_factory() as session:
                session.add(event)
                await session.commit()
        return True
    except Exception:
        log.warning("audit.write_failed", action=event.action)
        return False

"""Kullanıcı hesapları: parola karması (argon2id), doğrulama, kilitlenme (#278).

Henüz hiçbir uç bunu çağırmaz (giriş ekranı kararı #265'e bağlı); #266 oturum/belirteç katmanı
`verify_credentials` üzerine kurulacak.

Kurallar:
- Parola asla düz metin saklanmaz ve günlüğe yazılmaz (günlükte yalnızca hesap kimliği).
- Doğrulama sabit zamanlıdır: kullanıcı yoksa, hesap pasifse ya da kilitliyse de bir argon2id
  doğrulaması yapılır; böylece süre hesabın var olup olmadığını sızdırmaz.
- `MAX_FAILED_ATTEMPTS` yanlış denemede hesap `LOCK_MINUTES` dakika kilitlenir. Kilit sürerken
  doğru parola da reddedilir ve sayaç değişmez.
- Çağıran işlemi onaylar (`verify_credentials` flush eder, commit etmez).
"""

import asyncio
import secrets
import string
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import TooManyRequestsError
from app.core.ratelimit import RateLimiter
from app.db.models.accounts import AdminAccount, OwnerAccount
from app.db.models.external import Customer
from app.domain.accounts import (
    LOCK_MINUTES,
    MAX_FAILED_ATTEMPTS,
    MIN_PASSWORD_LENGTH,
    AccountRole,
)

log = structlog.get_logger(__name__)

Account = AdminAccount | OwnerAccount

# argon2-cffi varsayılanı argon2id'dir (RFC 9106 düşük bellek profili).
_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("kullanici-yok-sabit-sure-icin-sahte-parola")

_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "-_.!?#%+="
_TR_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosucgiosuaiu")


class PasswordPolicyError(ValueError):
    """Parola politikasına uymuyor (en az `MIN_PASSWORD_LENGTH` karakter)."""


class EmailTakenError(Exception):
    """E-posta başka bir tekne sahibi hesabında kayıtlı (kayıtta 409)."""


class LoginFailure(StrEnum):
    """İç neden (günlük ve test içindir). Dışarıya hepsi aynı genel mesajla döner (#266)."""

    UNKNOWN_USER = "bilinmeyen_kullanici"
    WRONG_PASSWORD = "yanlis_parola"
    INACTIVE = "pasif_hesap"
    LOCKED = "kilitli"


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    failure: LoginFailure | None = None
    account_id: UUID | None = None
    role: AccountRole | None = None
    customer_id: UUID | None = None
    just_locked: bool = False
    display_name: str | None = None


def validate_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.")


def hash_password(password: str) -> str:
    """Politikayı denetler, argon2id karması döner (`$argon2id$...`)."""
    validate_password_policy(password)
    return _hasher.hash(password)


def generate_password(length: int = 20) -> str:
    """Kriptografik rastgele parola (seed için)."""
    length = max(length, MIN_PASSWORD_LENGTH)
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def normalize_username(username: str) -> str:
    return username.strip().lower()


def derive_username(full_name: str, taken: set[str]) -> str:
    """Müşteri adından kullanıcı adı: "Ahmet Yılmaz" → "ahmet.yilmaz"; çakışmada sayı eki."""
    folded = unicodedata.normalize("NFKD", full_name.translate(_TR_FOLD)).lower()
    parts = ["".join(c for c in word if c.isascii() and c.isalnum()) for word in folded.split()]
    base = ".".join(p for p in parts if p) or "kullanici"
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}{n}"
    taken.add(candidate)
    return candidate


def _verify_hash(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def evaluate_login(account: Account | None, password: str, now: datetime) -> LoginResult:
    """Giriş kararını verir ve sayaç/kilit alanlarını günceller (veritabanına dokunmaz)."""
    if account is None:
        _verify_hash(_DUMMY_HASH, password)  # süre, hesabın varlığını belli etmesin
        return LoginResult(False, LoginFailure.UNKNOWN_USER)

    if account.locked_until is not None and account.locked_until <= now:
        account.locked_until = None  # kilit süresi doldu: sayaç sıfırdan başlar
        account.failed_attempts = 0

    if account.locked_until is not None:
        _verify_hash(_DUMMY_HASH, password)  # kilit sürerken doğru parola da geçmez
        return LoginResult(False, LoginFailure.LOCKED, account_id=account.id)

    if not account.is_active:
        _verify_hash(_DUMMY_HASH, password)
        return LoginResult(False, LoginFailure.INACTIVE, account_id=account.id)

    if not _verify_hash(account.password_hash, password):
        account.failed_attempts += 1
        locked = account.failed_attempts >= MAX_FAILED_ATTEMPTS
        if locked:
            account.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        return LoginResult(
            False, LoginFailure.WRONG_PASSWORD, account_id=account.id, just_locked=locked
        )

    account.failed_attempts = 0
    account.locked_until = None
    if _hasher.check_needs_rehash(account.password_hash):
        account.password_hash = _hasher.hash(password)  # parametreler güçlendiyse yenile
        account.password_changed_at = now
    return LoginResult(
        True,
        account_id=account.id,
        role=AccountRole.OWNER if isinstance(account, OwnerAccount) else AccountRole.ADMIN,
        customer_id=account.customer_id if isinstance(account, OwnerAccount) else None,
        display_name=getattr(account, "display_name", None),
    )


def _table(role: AccountRole) -> type[Account]:
    return OwnerAccount if role is AccountRole.OWNER else AdminAccount


async def verify_credentials(
    session: AsyncSession,
    role: AccountRole,
    username: str,
    password: str,
    *,
    now: datetime | None = None,
) -> LoginResult:
    """Seçilen rolün tablosunda kullanıcı adı + parolayı doğrular.

    Rol hangi tabloya bakılacağını belirler: yönetici parolası `owner` rolüyle (ve tersi)
    asla çalışmaz. Başarısız denemeyi sayar, gerekirse hesabı kilitler.
    """
    now = now or datetime.now(UTC)
    model = _table(role)
    account: Account | None = await session.scalar(
        select(model).where(model.username == normalize_username(username)).with_for_update()
    )
    # argon2id CPU/bellek yoğundur: olay döngüsünü (tüm istekleri) bloklamasın diye iş parçacığına
    # alınır (#266). `account` bu sırada yalnızca düz öznitelik atamasıyla değişir (G/Ç yok);
    # satır kilidi (`FOR UPDATE`) işlem bitene dek sürdüğünden aynı hesapta yarış olmaz.
    result = await asyncio.to_thread(evaluate_login, account, password, now)
    if account is not None:
        await session.flush()
    if result.just_locked:
        log.warning(
            "accounts.locked", account_id=str(result.account_id), role=role, minutes=LOCK_MINUTES
        )
    elif not result.ok:
        log.info(
            "accounts.login_failed",
            reason=result.failure,
            role=role,
            account_id=str(result.account_id),
        )
    return result


async def create_account(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    role: AccountRole,
    customer_id: UUID | None = None,
    display_name: str | None = None,
) -> Account:
    """Hesap oluşturur (parola politikası denetlenir, karması saklanır)."""
    common = {
        "username": normalize_username(username),
        "password_hash": hash_password(password),
        "failed_attempts": 0,
        "is_active": True,
    }
    account: Account
    if role is AccountRole.OWNER:
        if customer_id is None:
            raise ValueError("Tekne sahibi hesabı için customer_id zorunludur.")
        account = OwnerAccount(**common, customer_id=customer_id)
    else:
        if customer_id is not None:
            raise ValueError("Yönetici hesabı bir müşteriye bağlanamaz.")
        account = AdminAccount(**common, display_name=display_name or common["username"])
    session.add(account)
    await session.flush()
    return account


async def register_owner(
    session: AsyncSession, *, full_name: str, phone: str, email: str, password: str
) -> tuple[OwnerAccount, Customer]:
    """Kaydol (#382): tek işlemde müşteri satırı + tekne sahibi hesabı (e-posta = kullanıcı adı).

    E-posta zaten kayıtlıysa `EmailTakenError`; parola politikası `PasswordPolicyError`.
    Çağıran işlemi onaylar. Hesap hiçbir koşulda yönetici olmaz.
    """
    username = normalize_username(email)
    validate_password_policy(password)
    if await session.scalar(select(OwnerAccount.id).where(OwnerAccount.username == username)):
        raise EmailTakenError
    password_hash = await asyncio.to_thread(_hasher.hash, password)
    customer = Customer(full_name=full_name, phone=phone, email=username)
    session.add(customer)
    await session.flush()
    account = OwnerAccount(
        username=username,
        password_hash=password_hash,
        customer_id=customer.id,
        failed_attempts=0,
        is_active=True,
    )
    session.add(account)
    try:
        await session.flush()
    except IntegrityError as exc:  # eşzamanlı aynı e-posta
        raise EmailTakenError from exc
    return account, customer


# --- IP başına giriş denemesi sınırı (#266) ---------------------------------------------------
# Hesap kilidi (5 yanlışta 15 dk) tek başına bir saldırganın bilinen bir kullanıcı adını sürekli
# kilitlemesine (hizmet engelleme) izin verir. Giriş ucu açıldığında şu iki yardımcı kullanılır:
# kaynak IP'nin başarısız deneme bütçesi dolunca parola doğrulamasına hiç girilmez (hem hesap
# kilidi sayacı hem argon2 maliyeti korunur). Kalan risk: çok sayıda IP'den dağıtık saldırı
# hesabı yine kilitleyebilir; bu risk belgelenmiştir (docs/guvenlik_mimarisi.md).


async def enforce_login_ip_limit(
    limiter: RateLimiter | None, ip: str, *, limit: int, window_s: int
) -> None:
    """IP'nin başarısız giriş bütçesi dolduysa `TooManyRequestsError` fırlatır (sayaç artmaz)."""
    if limiter is None:
        return
    state = await limiter.peek(f"giris:{ip}", limit, window_s)
    if not state.allowed:
        raise TooManyRequestsError(
            "Çok fazla başarısız giriş denemesi; lütfen bekleyin.",
            retry_after_s=state.retry_after_s,
        )


async def record_login_failure_ip(
    limiter: RateLimiter | None, ip: str, *, limit: int, window_s: int
) -> None:
    """Başarısız giriş denemesini IP bütçesine yazar (başarılı girişte çağrılmaz)."""
    if limiter is not None:
        await limiter.hit(f"giris:{ip}", limit, window_s)

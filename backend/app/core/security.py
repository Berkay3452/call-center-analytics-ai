"""Kimlik doğrulama: Servis Anahtarı (`X-Service-Key`) ve kullanıcı kimliği (`X-User-Id`).

Mevcut Miço Usta .NET API'si, Python AI servisini paylaşılan servis anahtarı (`X-Service-Key`)
ile çağırır ve tekne sahibinin kimliğini ayrı bir başlıkta (`X-User-Id`) iletir (Mimari v3.1 §8).
Anahtar sabit zamanlı karşılaştırma (`secrets.compare_digest`) ile doğrulanır.
"""

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import AppError, ServiceUnavailableError, UnauthorizedError

SERVICE_KEY_HEADER = "X-Service-Key"
USER_ID_HEADER = "X-User-Id"
USER_SIGNATURE_HEADER = "X-User-Signature"
# Saat farkı payı: imzalayan sunucunun saati biraz ileride olabilir.
_FUTURE_SKEW_S = 5


class ServiceCaller(BaseModel):
    """Doğrulanmış servis çağrısı bağlamı.

    Admin uçlarında `owner_id` isteğe bağlıdır (`None` olabilir);
    tekne sahibi uçlarında `X-User-Id` başlığı zorunludur ve `owner_id` dolu gelir.
    """

    authenticated: bool = True
    owner_id: str | None = None


def verify_service_key(provided_key: str | None, settings: Settings) -> None:
    """`X-Service-Key` başlığını sabit zamanlı karşılaştırma ile doğrular."""
    if settings.auth_dev_bypass:
        # Yalnızca local/test (Settings doğrulayıcısı garanti eder).
        return

    if not provided_key:
        raise UnauthorizedError("Servis anahtarı eksik.")

    if settings.service_api_key is None or not settings.service_api_key.get_secret_value():
        raise ServiceUnavailableError("Kimlik doğrulama yapılandırılmamış (SERVICE_API_KEY eksik).")

    candidates = [settings.service_api_key.get_secret_value()]
    previous = settings.service_api_key_previous
    if previous is not None and _still_valid(settings.service_api_key_previous_expires_at):
        # Rotasyon penceresi: eski anahtar bitiş zamanına kadar kabul edilir (#266).
        candidates.append(previous.get_secret_value())
    provided = provided_key.encode("utf-8")
    # Her aday için karşılaştırma yapılır (erken çıkış yok): süre hangisinin eşleştiğini sızdırmaz.
    matches = [secrets.compare_digest(provided, c.encode("utf-8")) for c in candidates]
    if not any(matches):
        raise UnauthorizedError("Geçersiz servis anahtarı.")


def _still_valid(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return datetime.now(UTC) < expires_at


class UserSignatureError(UnauthorizedError):
    """İmzalı kullanıcı kimliği doğrulanamadı; `reason` denetim günlüğüne yazılır."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def sign_user_id(user_id: str, key: str, timestamp: int | None = None) -> str:
    """`X-User-Signature` değeri üretir: `<unix_zaman>.<hex(HMAC-SHA256(user_id.zaman))>`."""
    ts = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(key.encode("utf-8"), f"{user_id}.{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"


def verify_user_signature(
    raw_user_id: str | None, signature: str | None, settings: Settings, *, now: float | None = None
) -> None:
    """İmzalı `X-User-Id` doğrulaması (#266).

    `X-User-Id` yoksa (yönetici bağlamı) imza aranmaz. Varsa: `user_signature_required` açıkken
    imza zorunludur; kapalıyken (yalnızca local/test) gönderilmiş imza yine doğrulanır.
    Süresi geçmiş veya geleceğe ait zaman damgası reddedilir (tekrar oynatma penceresi kısadır).
    """
    if raw_user_id is None or not raw_user_id.strip():
        return
    if not signature:
        if settings.user_signature_required:
            raise UserSignatureError("imza_eksik", "Kullanıcı kimliği imzası eksik.")
        return
    ts_text, _, mac = signature.partition(".")
    if not ts_text.isdigit() or not mac:
        raise UserSignatureError("imza_gecersiz", "Kullanıcı kimliği imzası geçersiz.")
    ts = int(ts_text)
    current = time.time() if now is None else now
    keys: list[str] = []
    current_key = settings.user_signing_key.get_secret_value() if settings.user_signing_key else ""
    if current_key:
        keys.append(current_key)
    prev = settings.user_signing_key_previous
    if (
        prev is not None
        and prev.get_secret_value()
        and _still_valid(settings.user_signing_key_previous_expires_at)
    ):
        keys.append(prev.get_secret_value())
    if not keys:
        raise ServiceUnavailableError("Kimlik imzası yapılandırılmamış (USER_SIGNING_KEY eksik).")
    message = f"{raw_user_id.strip()}.{ts}".encode()
    matches = [
        hmac.compare_digest(
            hmac.new(k.encode("utf-8"), message, hashlib.sha256).hexdigest().encode(),
            mac.encode("utf-8"),
        )
        for k in keys
    ]
    if not any(matches):
        raise UserSignatureError("imza_gecersiz", "Kullanıcı kimliği imzası geçersiz.")
    age = current - ts
    if age > settings.user_signature_max_age_s or age < -_FUTURE_SKEW_S:
        raise UserSignatureError("imza_suresi_doldu", "Kullanıcı kimliği imzasının süresi doldu.")


def normalize_user_id(raw_user_id: str | None) -> str | None:
    """`X-User-Id` değerini UUID olarak doğrular (veritabanında `owner_id` UUID'dir).

    Boş değer `None` döner; dolu ama UUID olmayan değer 400 hatasıdır.
    """
    if raw_user_id is None or not raw_user_id.strip():
        return None
    try:
        return str(UUID(raw_user_id.strip()))
    except ValueError:
        raise AppError("Kullanıcı kimliği (X-User-Id) geçerli bir UUID olmalıdır.") from None


def require_owner_id_value(raw_user_id: str | None) -> str:
    """Tekne sahibi uçları için `X-User-Id` başlığının dolu ve geçerli olduğunu doğrular."""
    owner_id = normalize_user_id(raw_user_id)
    if owner_id is None:
        raise AppError("Tekne sahibi kimliği (X-User-Id) zorunludur.")
    return owner_id

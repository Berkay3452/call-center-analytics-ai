"""Kimlik doğrulama: Servis Anahtarı (`X-Service-Key`) ve kullanıcı kimliği (`X-User-Id`).

Mevcut Miço Usta .NET API'si, Python AI servisini paylaşılan servis anahtarı (`X-Service-Key`)
ile çağırır ve tekne sahibinin kimliğini ayrı bir başlıkta (`X-User-Id`) iletir (Mimari v3.1 §8).
Anahtar sabit zamanlı karşılaştırma (`secrets.compare_digest`) ile doğrulanır.
"""

import secrets

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import AppError, ServiceUnavailableError, UnauthorizedError

SERVICE_KEY_HEADER = "X-Service-Key"
USER_ID_HEADER = "X-User-Id"


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

    expected = settings.service_api_key.get_secret_value()
    is_valid = secrets.compare_digest(
        provided_key.encode("utf-8"),
        expected.encode("utf-8"),
    )
    if not is_valid:
        raise UnauthorizedError("Geçersiz servis anahtarı.")


def require_owner_id_value(raw_user_id: str | None) -> str:
    """Tekne sahibi uçları için `X-User-Id` başlığının dolu olduğunu doğrular."""
    if raw_user_id is None or not raw_user_id.strip():
        raise AppError("Tekne sahibi kimliği (X-User-Id) zorunludur.")
    return raw_user_id.strip()

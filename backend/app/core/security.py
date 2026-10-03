"""Kimlik doğrulama: Supabase Auth JWT'lerinin JWKS ile doğrulanması.

Frontend, Supabase'ten aldığı access token'ı `Authorization: Bearer <jwt>` ile gönderir.
Backend imzayı Supabase'in açık anahtarlarıyla (JWKS) doğrular;
parola hiçbir zaman backend'e gelmez.

Not: Backend veritabanına service-role ile bağlandığı için RLS'i atlar.
Bu yüzden yetki kontrolü (rol) mutlaka backend kodunda yapılır (bkz. api/deps.py).
"""

from functools import lru_cache
from typing import Literal
from uuid import UUID

import jwt
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError, UnauthorizedError

Role = Literal["admin", "analyst"]
_ALLOWED_ALGORITHMS = ["ES256", "RS256"]


class CurrentUser(BaseModel):
    id: UUID
    email: str | None = None
    role: Role = "analyst"


# Yerel geliştirmede (AUTH_DEV_BYPASS=true) kullanılan sabit kullanıcı.
DEV_USER = CurrentUser(
    id=UUID("00000000-0000-0000-0000-000000000001"), email="dev@local", role="admin"
)


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # Anahtarlar önbelleğe alınır; Supabase anahtar döndürürse otomatik yenilenir.
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


async def verify_access_token(token: str, settings: Settings) -> CurrentUser:
    jwks_url = settings.jwks_url
    if not jwks_url:
        raise ServiceUnavailableError("Kimlik doğrulama yapılandırılmamış (SUPABASE_URL eksik).")

    try:
        # PyJWKClient ağ çağrısı yapar ve senkrondur → event loop'u bloklamamak için thread'de.
        signing_key = await run_in_threadpool(
            _jwks_client(jwks_url).get_signing_key_from_jwt, token
        )
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALLOWED_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise ServiceUnavailableError("Kimlik doğrulama anahtarlarına ulaşılamadı.") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Geçersiz veya süresi dolmuş oturum.") from exc

    # TODO(Hafta 3): rol, `profiles` tablosundan okunacak. Şimdilik Supabase app_metadata'dan.
    app_metadata = claims.get("app_metadata") or {}
    role = app_metadata.get("role", "analyst")
    return CurrentUser(
        id=UUID(claims["sub"]),
        email=claims.get("email"),
        role=role if role in ("admin", "analyst") else "analyst",
    )

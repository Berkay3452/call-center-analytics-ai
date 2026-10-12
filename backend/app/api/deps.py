"""FastAPI bağımlılıkları: ayarlar, DB oturumu, Redis, servis anahtarı ve kullanıcı kimliği."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import (
    SERVICE_KEY_HEADER,
    USER_ID_HEADER,
    ServiceCaller,
    require_owner_id_value,
    verify_service_key,
)

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """İstek başına bir oturum. Commit/rollback kararı servis katmanındadır;
    istek hata ile biterse açık işlem otomatik geri alınır."""
    async with request.app.state.session_factory() as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def require_service_key(
    settings: SettingsDep,
    x_service_key: Annotated[str | None, Header(alias=SERVICE_KEY_HEADER)] = None,
    x_user_id: Annotated[str | None, Header(alias=USER_ID_HEADER)] = None,
) -> ServiceCaller:
    """Servis anahtarını doğrular; `X-User-Id` varsa bağlama ekler (admin uçlarında opsiyonel)."""
    verify_service_key(x_service_key, settings)
    normalized_owner_id = x_user_id.strip() if x_user_id and x_user_id.strip() else None
    return ServiceCaller(authenticated=True, owner_id=normalized_owner_id)


ServiceCallerDep = Annotated[ServiceCaller, Depends(require_service_key)]


async def require_owner_id(caller: ServiceCallerDep) -> str:
    """Tekne sahibi uçları için servis anahtarını ve zorunlu `X-User-Id` başlığını doğrular."""
    return require_owner_id_value(caller.owner_id)


OwnerIdDep = Annotated[str, Depends(require_owner_id)]

"""FastAPI bağımlılıkları: ayarlar, veritabanı oturumu, Redis, mevcut kullanıcı ve rol kontrolü."""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import DEV_USER, CurrentUser, Role, verify_access_token

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

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if settings.auth_dev_bypass:
        # Yalnızca local/test (Settings doğrulayıcısı garanti eder).
        return DEV_USER
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Oturum bulunamadı.")
    return await verify_access_token(credentials.credentials, settings)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(*roles: Role) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """Kullanım: `user: Annotated[CurrentUser, Depends(require_role("admin"))]`"""

    async def _checker(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise ForbiddenError("Bu işlem için yetkiniz yok.")
        return user

    return _checker

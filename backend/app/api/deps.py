"""FastAPI bağımlılıkları: ayarlar, DB oturumu, Redis, servis anahtarı ve kullanıcı kimliği."""

import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import (
    SERVICE_KEY_HEADER,
    USER_ID_HEADER,
    ServiceCaller,
    normalize_user_id,
    require_owner_id_value,
    verify_service_key,
)
from app.domain.audit import AuditAction, AuditActorRole, AuditOutcome
from app.services.audit import record_audit_event_isolated
from app.storage.base import AudioStorage

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


def get_audio_storage(settings: SettingsDep) -> AudioStorage:
    from app.storage.registry import build_audio_storage

    return build_audio_storage(settings)


AudioStorageDep = Annotated[AudioStorage, Depends(get_audio_storage)]


def _endpoint_label(request: Request) -> str:
    """Uç nokta etiketi: rota şablonu (`/calls/{call_id}` → `calls.call_id`), ham yol değil."""
    route = request.scope.get("route")
    template = getattr(route, "path", None) or "bilinmeyen"
    return re.sub(r"[^A-Za-z0-9_.:-]+", ".", template).strip(".")[:64] or "bilinmeyen"


async def require_service_key(
    request: Request,
    settings: SettingsDep,
    x_service_key: Annotated[str | None, Header(alias=SERVICE_KEY_HEADER)] = None,
    x_user_id: Annotated[str | None, Header(alias=USER_ID_HEADER)] = None,
) -> ServiceCaller:
    """Servis anahtarını doğrular; `X-User-Id` varsa bağlama ekler (admin uçlarında opsiyonel).

    Başarısız doğrulama denetim günlüğüne yazılır (#267): anahtar değeri veya başlık içeriği değil,
    yalnızca neden (`eksik` | `gecersiz`), yol ve istek kimliği/IP kaydedilir.
    """
    try:
        verify_service_key(x_service_key, settings)
    except UnauthorizedError as exc:
        factory = getattr(request.app.state, "session_factory", None)
        if factory is not None and settings.audit_auth_failures:
            await record_audit_event_isolated(
                factory,
                action=AuditAction.KIMLIK_DOGRULAMA_BASARISIZ,
                actor_role=AuditActorRole.ANONIM,
                target_type="endpoint",
                target_id=_endpoint_label(request),
                outcome=AuditOutcome.REDDEDILDI,
                details={"neden": "eksik" if not x_service_key else "gecersiz"},
            )
        raise exc
    return ServiceCaller(authenticated=True, owner_id=normalize_user_id(x_user_id))


ServiceCallerDep = Annotated[ServiceCaller, Depends(require_service_key)]


async def require_admin(caller: ServiceCallerDep) -> ServiceCaller:
    """Yönetici bağlamı: servis anahtarı doğru ve `X-User-Id` YOK.

    Hesap/rol sistemi (#278, #275) gelene kadar "yönetici" = tekne sahibi kimliği taşımayan
    servis çağrısıdır (Miço Usta arka ucu veya yönetici arayüzünün vekil rotası). Tekne sahibi
    kimliğiyle gelen çağrı 403 alır. Rol denetimi #275'te gerçek rollere bağlanacak.
    """
    if caller.owner_id is not None:
        raise ForbiddenError("Bu uç yalnızca yönetici bağlamında kullanılabilir.")
    return caller


AdminCallerDep = Annotated[ServiceCaller, Depends(require_admin)]


async def require_owner_id(caller: ServiceCallerDep) -> str:
    """Tekne sahibi uçları için servis anahtarını ve zorunlu `X-User-Id` başlığını doğrular."""
    return require_owner_id_value(caller.owner_id)


OwnerIdDep = Annotated[str, Depends(require_owner_id)]

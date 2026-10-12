"""Servis anahtarı (`X-Service-Key`) ve tekne sahibi kimliği (`X-User-Id`) doğrulama uçları."""

from fastapi import APIRouter

from app.api.deps import OwnerIdDep, ServiceCallerDep
from app.core.security import ServiceCaller
from app.schemas.common import ErrorResponse

router = APIRouter(tags=["auth"])


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

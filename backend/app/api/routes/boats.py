"""Tekne sahibi uçları (#383): kendi teknelerini listele ve ekle (yönetici 403)."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.api.deps import OwnerIdDep, SessionDep
from app.domain.audit import AuditAction, AuditActorRole
from app.schemas.api import BoatCreate, BoatOut
from app.schemas.common import ErrorResponse
from app.services import boats as boat_service
from app.services.audit import record_audit_event_isolated

router = APIRouter(prefix="/boats", tags=["boats"])


@router.get(
    "",
    response_model=list[BoatOut],
    summary="Teknelerim",
    operation_id="listMyBoats",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def list_my_boats(owner_id: OwnerIdDep, session: SessionDep) -> list[BoatOut]:
    rows = await boat_service.list_boats(session, UUID(owner_id))
    return [BoatOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "",
    response_model=BoatOut,
    status_code=201,
    summary="Tekne ekle",
    operation_id="addMyBoat",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def add_my_boat(
    body: BoatCreate, owner_id: OwnerIdDep, session: SessionDep, request: Request
) -> BoatOut:
    """Oturumdaki sahibin adına tekne ekler; `owner_id` istekten alınmaz (BOLA yok)."""
    boat = await boat_service.add_boat(
        session,
        UUID(owner_id),
        name=body.name,
        model=body.model,
        year=body.year,
        marina=body.marina,
    )
    await session.commit()
    await record_audit_event_isolated(
        request.app.state.session_factory,
        action=AuditAction.TEKNE_EKLENDI,
        actor_id=UUID(owner_id),
        actor_role=AuditActorRole.TEKNE_SAHIBI,
        target_type="tekne",
        target_id=boat.id,
    )
    return BoatOut.model_validate(boat, from_attributes=True)

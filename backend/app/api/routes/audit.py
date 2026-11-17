"""Denetim günlüğü okuma ucu (#267): yalnızca yönetici bağlamı, yalnızca okuma.

Yazma ucu yoktur: kayıtlar iş akışlarında `record_audit_event` ile düşer. Sözleşme: docs/api.md.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import ColumnElement, func, select

from app.api.deps import AdminCallerDep, SessionDep
from app.db.models.audit import AuditLog
from app.domain.audit import AuditAction
from app.schemas.audit import AuditLogFilters, AuditLogItem
from app.schemas.common import ErrorResponse, Page
from app.services.audit import record_audit_event

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get(
    "",
    response_model=Page[AuditLogItem],
    summary="Denetim günlüğü (yönetici)",
    operation_id="listAuditLog",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def list_audit_log(
    caller: AdminCallerDep,
    session: SessionDep,
    filters: Annotated[AuditLogFilters, Query()],
) -> Page[AuditLogItem]:
    """Denetim kayıtlarını en yeni başta olacak şekilde sayfalı döndürür.

    Kayıtlar yalnızca eklenir; silme veya güncelleme ucu yoktur. Günlüğün görüntülenmesi de
    `denetim_goruntulendi` olayı olarak kaydedilir.
    """
    conditions: list[ColumnElement[bool]] = []
    if filters.action:
        conditions.append(AuditLog.action == filters.action.value)
    if filters.outcome:
        conditions.append(AuditLog.outcome == filters.outcome.value)
    if filters.actor_id:
        conditions.append(AuditLog.actor_id == filters.actor_id)
    if filters.target_type:
        conditions.append(AuditLog.target_type == filters.target_type)
    if filters.target_id:
        conditions.append(AuditLog.target_id == filters.target_id)
    if filters.since:
        conditions.append(AuditLog.occurred_at >= filters.since)
    if filters.until:
        conditions.append(AuditLog.occurred_at < filters.until)

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
            .limit(filters.page_size)
            .offset((filters.page - 1) * filters.page_size)
        )
    ).all()
    items = [AuditLogItem.model_validate(r) for r in rows]
    await record_audit_event(
        session,
        action=AuditAction.DENETIM_GORUNTULENDI,
        actor=caller,
        target_type="audit_log",
        details={"sonuc_sayisi": len(items), "sayfa": filters.page},
    )
    await session.commit()
    return Page[AuditLogItem](
        items=items, total=total or 0, page=filters.page, page_size=filters.page_size
    )

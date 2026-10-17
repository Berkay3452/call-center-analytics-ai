"""CRM kayıt ve öneri uçları (#51): sayfalı liste.

Sözleşme: docs/api.md.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query

from app.api.deps import ServiceCallerDep, SessionDep
from app.schemas.api import (
    CallFilters,
    CrmApproveIn,
    CrmRecordItem,
    CrmRejectIn,
    CrmReviewOut,
)
from app.schemas.common import ErrorResponse, Page
from app.services import call_reader, crm_review_service

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get(
    "",
    response_model=Page[CrmRecordItem],
    summary="CRM öneri ve kayıtları",
    operation_id="listCrmRecords",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def list_crm_records(
    _: ServiceCallerDep,
    session: SessionDep,
    filters: Annotated[CallFilters, Query()],
) -> Page[CrmRecordItem]:
    """Analiz edilmiş çağrılardan çıkarılan CRM önerilerini sayfalı olarak döndürür."""
    return await call_reader.list_crm_records(session, filters)


@router.post(
    "/{call_id}/approve",
    response_model=CrmReviewOut,
    summary="CRM önerisini onayla",
    operation_id="approveCrmRecord",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def approve_crm_record(
    call_id: UUID,
    _: ServiceCallerDep,
    session: SessionDep,
    payload: Annotated[CrmApproveIn | None, Body()] = None,
) -> CrmReviewOut:
    """CRM önerisini onaylar veya isteğe bağlı 7 alanı düzenleyerek onaylar (#106).

    Çağrının müşteri ve tekne kaydı eşleşmişse servis emri oluşturulur.
    Eşleşme yoksa 409 döner. Tekrar onay aynı servis emrini döner (idempotent).
    """
    return await crm_review_service.approve_crm_record(session, call_id, payload or CrmApproveIn())


@router.post(
    "/{call_id}/reject",
    response_model=CrmReviewOut,
    summary="CRM önerisini reddet",
    operation_id="rejectCrmRecord",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def reject_crm_record(
    call_id: UUID,
    _: ServiceCallerDep,
    session: SessionDep,
    payload: Annotated[CrmRejectIn | None, Body()] = None,
) -> CrmReviewOut:
    """CRM önerisini gerekçe/not ile reddeder (#106)."""
    return await crm_review_service.reject_crm_record(session, call_id, payload or CrmRejectIn())

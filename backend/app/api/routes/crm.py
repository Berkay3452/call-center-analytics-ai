"""CRM kayıt ve öneri uçları (#51): sayfalı liste.

Sözleşme: docs/api.md.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ServiceCallerDep, SessionDep
from app.schemas.api import CallFilters, CrmRecordItem
from app.schemas.common import ErrorResponse, Page
from app.services import call_reader

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

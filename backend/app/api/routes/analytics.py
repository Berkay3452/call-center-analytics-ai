"""KPI ve çağrı analitiği uçları (#52).

Sözleşme: docs/api.md.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ServiceCallerDep, SessionDep
from app.schemas.analysis import KpiSummary
from app.schemas.api import PeriodFilter
from app.schemas.common import ErrorResponse
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/summary",
    response_model=KpiSummary,
    summary="KPI ve analitik özeti",
    operation_id="getKpiSummary",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def get_kpi_summary(
    _: ServiceCallerDep,
    session: SessionDep,
    filter_params: Annotated[PeriodFilter, Query()],
) -> KpiSummary:
    """Belirtilen dönem için çağrı analitiği ve satış KPI özetini döndürür."""
    return await analytics_service.get_kpi_summary(session, filter_params)

"""Çağrı alma ve analiz uçları (#48): çağrı oluştur, analizi başlat, durumu sorgula.

Okuma uçları (liste, detay) `calls.py`'dedir (#51). Sözleşme: docs/api.md.
"""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status

from app.api.deps import ServiceCallerDep, SessionDep
from app.core.errors import ServiceUnavailableError
from app.schemas.api import CallAccepted, CallCreate, CallStatus
from app.schemas.common import ErrorResponse
from app.services import call_ingest

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])

Enqueue = Callable[[UUID], str | None]


def get_enqueue() -> Enqueue:
    """Analiz görevini kuyruğa atan fonksiyon (testlerde değiştirilir)."""

    def enqueue(call_id: UUID) -> str | None:
        from app.workers.tasks.analysis import analyze_call

        return analyze_call.delay(str(call_id)).id

    return enqueue


EnqueueDep = Annotated[Enqueue, Depends(get_enqueue)]


async def _enqueue_or_fail(session: SessionDep, enqueue: Enqueue, call_id: UUID) -> CallAccepted:
    try:
        task_id = enqueue(call_id)
    except Exception as exc:  # Redis/broker kapalı
        log.exception("analysis.enqueue_failed", call_id=str(call_id))
        await call_ingest.set_state(session, call_id, "basarisiz", "Analiz kuyruğa alınamadı.")
        await session.commit()
        raise ServiceUnavailableError("Analiz kuyruğuna ulaşılamadı.") from exc
    return CallAccepted(call_id=call_id, state="beklemede", task_id=task_id)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CallAccepted,
    responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_call(
    payload: CallCreate, _: ServiceCallerDep, session: SessionDep, enqueue: EnqueueDep
) -> CallAccepted:
    """Transkriptli çağrıyı kaydeder ve analizi arka planda başlatır."""
    call_id = await call_ingest.create_call(session, payload)
    await session.commit()  # görev başlamadan kayıt görünür olmalı
    return await _enqueue_or_fail(session, enqueue, call_id)


@router.post(
    "/{call_id}/analyze",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CallAccepted,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def analyze_call(
    call_id: UUID, _: ServiceCallerDep, session: SessionDep, enqueue: EnqueueDep
) -> CallAccepted:
    """Çağrıyı yeniden analiz eder (yeni analiz sürümü eklenir)."""
    await call_ingest.request_analysis(session, call_id)
    await session.commit()
    return await _enqueue_or_fail(session, enqueue, call_id)


@router.get(
    "/{call_id}/status",
    response_model=CallStatus,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def call_status(call_id: UUID, _: ServiceCallerDep, session: SessionDep) -> CallStatus:
    """İşlenme durumu; arayüz bitene kadar birkaç saniyede bir sorar."""
    return await call_ingest.get_status(session, call_id)

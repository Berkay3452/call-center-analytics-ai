"""Çağrı alma ve analiz uçları (#48, #49): çağrı oluştur (metin veya ses), yeniden işle, durum.

Okuma uçları (liste, detay) `calls.py`'dedir (#51). Sözleşme: docs/api.md.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import AudioStorageDep, ServiceCallerDep, SessionDep, SettingsDep
from app.core.errors import ServiceUnavailableError
from app.domain.enums import SwitchboardOutcome
from app.schemas.api import AudioCallMeta, CallAccepted, CallCreate, CallStatus
from app.schemas.common import ErrorResponse
from app.services import audio_ingest, call_ingest
from app.services.call_ingest import AnalysisKind

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])

# (çağrı, görev türü) → görev kimliği. "stt": sesi yazıya çevir (sonra analiz), "analysis": analiz.
Enqueue = Callable[[UUID, AnalysisKind], str | None]


def get_enqueue() -> Enqueue:
    """Görevi Celery kuyruğuna atan fonksiyon (testlerde değiştirilir)."""

    def enqueue(call_id: UUID, kind: AnalysisKind) -> str | None:
        if kind == "stt":
            from app.workers.tasks.stt import transcribe_audio

            return transcribe_audio.delay(str(call_id)).id
        from app.workers.tasks.analysis import analyze_call

        return analyze_call.delay(str(call_id)).id

    return enqueue


EnqueueDep = Annotated[Enqueue, Depends(get_enqueue)]


async def _enqueue_or_fail(
    session: SessionDep, enqueue: Enqueue, call_id: UUID, kind: AnalysisKind
) -> CallAccepted:
    try:
        task_id = enqueue(call_id, kind)
    except Exception as exc:  # Redis/broker kapalı
        log.exception("task.enqueue_failed", call_id=str(call_id), kind=kind)
        await call_ingest.set_state(session, call_id, "basarisiz", "Görev kuyruğa alınamadı.")
        await session.commit()
        raise ServiceUnavailableError("İş kuyruğuna ulaşılamadı.") from exc
    return CallAccepted(call_id=call_id, state="beklemede", task_id=task_id)


_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CallAccepted,
    responses={k: v for k, v in _ERRORS.items() if k != 404},
)
async def create_call(
    payload: CallCreate, _: ServiceCallerDep, session: SessionDep, enqueue: EnqueueDep
) -> CallAccepted:
    """Transkriptli çağrıyı kaydeder ve analizi arka planda başlatır."""
    call_id = await call_ingest.create_call(session, payload)
    await session.commit()  # görev başlamadan kayıt görünür olmalı
    return await _enqueue_or_fail(session, enqueue, call_id, "analysis")


@router.post(
    "/audio",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CallAccepted,
    responses={
        **{k: v for k, v in _ERRORS.items() if k != 404},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
    },
)
async def create_audio_call(
    file: Annotated[UploadFile, File(description="Çağrı ses kaydı (wav, mp3, m4a...)")],
    started_at: Annotated[datetime, Form()],
    _: ServiceCallerDep,
    session: SessionDep,
    settings: SettingsDep,
    storage: AudioStorageDep,
    enqueue: EnqueueDep,
    duration_s: Annotated[int | None, Form(ge=0)] = None,
    answer_delay_s: Annotated[int | None, Form(ge=0)] = None,
    switchboard_outcome: Annotated[SwitchboardOutcome | None, Form()] = None,
    customer_name: Annotated[str | None, Form()] = None,
    customer_phone: Annotated[str | None, Form()] = None,
    boat_name: Annotated[str | None, Form()] = None,
    boat_model: Annotated[str | None, Form()] = None,
    marina: Annotated[str | None, Form()] = None,
) -> CallAccepted:
    """Ses kaydını saklar; yazıya çevirme (STT) ve ardından analiz arka planda çalışır.

    Aynı ses daha önce yüklendiyse 409 döner (`details.call_id` mevcut çağrıdır).
    Form alanları `AudioCallMeta` ile aynıdır (FastAPI dosya + model formunu birlikte açamadığı
    için alanlar tek tek alınır).
    """
    meta = AudioCallMeta(
        started_at=started_at,
        duration_s=duration_s,
        answer_delay_s=answer_delay_s,
        switchboard_outcome=switchboard_outcome,
        customer_name=customer_name or None,
        customer_phone=customer_phone or None,
        boat_name=boat_name or None,
        boat_model=boat_model or None,
        marina=marina or None,
    )
    stored = await run_in_threadpool(
        audio_ingest.store_audio,
        file.file,
        file.filename,
        storage,
        max_bytes=settings.audio_max_mb * 1024 * 1024,
    )
    call_id = await audio_ingest.create_audio_call(session, meta, stored)
    await session.commit()
    log.info("call.audio_received", call_id=str(call_id), size=stored.size_bytes)
    return await _enqueue_or_fail(session, enqueue, call_id, "stt")


@router.post(
    "/{call_id}/analyze",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CallAccepted,
    responses=_ERRORS,
)
async def analyze_call(
    call_id: UUID, _: ServiceCallerDep, session: SessionDep, enqueue: EnqueueDep
) -> CallAccepted:
    """Çağrıyı yeniden işler: transkript varsa yeni analiz sürümü, yoksa sesi yeniden çevirir."""
    kind = await call_ingest.request_analysis(session, call_id)
    await session.commit()
    return await _enqueue_or_fail(session, enqueue, call_id, kind)


@router.get(
    "/{call_id}/status",
    response_model=CallStatus,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def call_status(call_id: UUID, _: ServiceCallerDep, session: SessionDep) -> CallStatus:
    """İşlenme durumu; arayüz bitene kadar birkaç saniyede bir sorar."""
    return await call_ingest.get_status(session, call_id)

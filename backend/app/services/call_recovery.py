"""Takılı kalan çağrıları kurtarma servisi (#107).

İşçi süreçlerinin (Celery worker) çökmesi, yeniden başlaması veya aşırı yük nedeniyle
'beklemede', 'yaziya_cevriliyor' veya 'isleniyor' durumunda asılı kalan çağrıları tarar:
- İlk tespitte: Çağrıyı bir kez yeniden kuyruğa alır (`beklemede` yapar ve
  stt/analiz görevini tetikler).
- İkinci tespitte: Çağrıyı `basarisiz` yapar ve `error` alanına
  'İşlem zaman aşımına uğradı, yeniden deneyin' yazar. Böylece kullanıcı arayüzünde
  'Yeniden Analiz Et' butonu aktifleşir.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.ai import Call, Transcript

log = structlog.get_logger(__name__)

STUCK_STATES = ("beklemede", "yaziya_cevriliyor", "isleniyor")
RETRY_MARKER_PREFIX = "İşlem zaman aşımı nedeniyle yeniden deneniyor"
FINAL_TIMEOUT_ERROR = "İşlem zaman aşımına uğradı, yeniden deneyin"


async def recover_stuck_calls(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    timeout_min: int = 10,
    enqueue: bool = True,
) -> dict[str, int]:
    """Zaman aşımına uğramış çağrıları tespit eder ve kurtarır veya başarısız olarak işaretler."""
    cutoff = datetime.now(UTC) - timedelta(minutes=timeout_min)

    async with session_factory() as session:
        stmt = (
            select(Call.id, Call.state, Call.error, Call.audio_path)
            .where(
                Call.state.in_(STUCK_STATES),
                Call.updated_at <= cutoff,
            )
            .order_by(Call.updated_at.asc())
        )
        result = await session.execute(stmt)
        candidates = list(result.all())

    retried = 0
    failed = 0

    for call_id, state, error, audio_path in candidates:
        is_second_timeout = bool(
            error
            and (
                error.startswith(RETRY_MARKER_PREFIX)
                or error == FINAL_TIMEOUT_ERROR
                or "zaman aşımı" in error.lower()
            )
        )

        async with session_factory() as session, session.begin():
            if is_second_timeout:
                await session.execute(
                    update(Call)
                    .where(Call.id == call_id)
                    .values(state="basarisiz", error=FINAL_TIMEOUT_ERROR, updated_at=func.now())
                )
                failed += 1
                log.warning(
                    "call.stuck_recovery_failed",
                    call_id=str(call_id),
                    previous_state=state,
                    error=FINAL_TIMEOUT_ERROR,
                )
            else:
                has_transcript = await session.scalar(
                    select(func.count())
                    .select_from(Transcript)
                    .where(Transcript.call_id == call_id)
                )
                needs_stt = bool(audio_path and not has_transcript)
                retry_error = f"{RETRY_MARKER_PREFIX} (deneme 1)"

                await session.execute(
                    update(Call)
                    .where(Call.id == call_id)
                    .values(state="beklemede", error=retry_error, updated_at=func.now())
                )
                retried += 1

                if enqueue:
                    _enqueue_recovery_task(call_id, needs_stt=needs_stt)

                log.info(
                    "call.stuck_recovered_requeued",
                    call_id=str(call_id),
                    previous_state=state,
                    needs_stt=needs_stt,
                )

    return {"retried": retried, "failed": failed, "total": len(candidates)}


def _enqueue_recovery_task(call_id: UUID, *, needs_stt: bool) -> None:
    try:
        if needs_stt:
            from app.workers.tasks.stt import transcribe_audio

            transcribe_audio.delay(str(call_id))
        else:
            from app.workers.tasks.analysis import analyze_call

            analyze_call.delay(str(call_id))
    except Exception as exc:
        log.warning(
            "call.stuck_requeue_failed",
            call_id=str(call_id),
            needs_stt=needs_stt,
            error=str(exc),
        )

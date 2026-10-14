"""Çağrı alma ve analiz çalıştırma (#48).

Akış: `create_call` çağrıyı ve (maskelenmiş) transkriptini kaydeder → API analizi kuyruğa alır →
Celery görevi `run_call_analysis` agent'ları çalıştırır, sonucu yazar ve çağrının durumunu
(`calls.state`) günceller. Ses dosyası akışı (#49) aynı fonksiyonları kullanır; STT'den gelen
segmentler `create_call`'a `segments` olarak verilir.

Durumlar: beklemede → (yaziya_cevriliyor) → isleniyor → tamam | kismi | basarisiz.
Her geçiş ayrı bir işlemde kaydedilir; arayüz `GET /calls/{id}/status` ile ilerlemeyi görür.
"""

from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.base import AnalysisContext, CallInfo, Segment
from app.agents.orchestrator import OrchestrationResult
from app.core.errors import ConflictError, NotFoundError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call, Transcript, TranscriptSegment
from app.schemas.api import CallCreate, CallState, CallStatus, SegmentIn
from app.services.analysis_store import save_analysis, save_transcript
from app.services.masking import mask_text
from app.services.transcript_text import parse_transcript, with_timings

log = structlog.get_logger(__name__)


class AnalysisRunner(Protocol):
    """Orkestratörün ihtiyaç duyulan yüzü; testler sahte bir uygulama verir."""

    async def run(self, ctx: AnalysisContext) -> OrchestrationResult: ...


class NoTranscriptError(ConflictError):
    """Analiz edilecek transkript yok."""

    code = "no_transcript"


async def create_call(session: AsyncSession, payload: CallCreate) -> UUID:
    """Çağrıyı ve transkriptini kaydeder (durum `beklemede`). Commit çağıranındır."""
    segments_in = payload.segments or parse_transcript(payload.transcript or "")
    if not segments_in:
        raise NoTranscriptError("Transkriptte konuşma satırı bulunamadı.")

    call = Call(
        started_at=payload.started_at,
        duration_s=payload.duration_s,
        answer_delay_s=payload.answer_delay_s,
        switchboard_outcome=payload.switchboard_outcome.value
        if payload.switchboard_outcome
        else None,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        boat_name=payload.boat_name,
        boat_model=payload.boat_model,
        marina=payload.marina,
        state="beklemede",
    )
    session.add(call)
    await session.flush()

    await store_segments(session, call.id, segments_in, names=[payload.customer_name])
    return call.id


async def store_segments(
    session: AsyncSession,
    call_id: UUID,
    segments_in: Sequence[SegmentIn],
    *,
    names: Sequence[str | None] = (),
) -> None:
    """Konuşma turlarını maskeleyip transkript olarak yazar (metinle gelen çağrı ve STT ortak)."""
    timed = with_timings(segments_in)
    segments = [
        Segment(
            idx=i,
            speaker=seg.speaker,
            start_ms=start,
            end_ms=end,
            text_masked=mask_text(seg.text, names),
        )
        for i, (seg, start, end) in enumerate(timed)
    ]
    await save_transcript(session, call_id, segments, raw_texts=[s.text for s, _, _ in timed])


async def set_state(
    session: AsyncSession, call_id: UUID, state: CallState, error: str | None = None
) -> None:
    await session.execute(update(Call).where(Call.id == call_id).values(state=state, error=error))


AnalysisKind = Literal["analysis", "stt"]


async def request_analysis(session: AsyncSession, call_id: UUID) -> AnalysisKind:
    """Çağrıyı (yeniden) işlemeye alır ve hangi görevin başlatılacağını döner. Commit çağıranındır.

    - Transkript varsa: yeniden analiz (`analysis`, yeni sürüm).
    - Transkript yok ama ses varsa (ör. STT hata vermişti): önce yazıya çevirme (`stt`).
    Çağrı yoksa 404; zaten işleniyorsa 409; ne transkript ne ses varsa 409.
    """
    call = await session.get(Call, call_id, with_for_update=True)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")
    if call.state in ("yaziya_cevriliyor", "isleniyor"):
        raise ConflictError("Çağrı şu anda işleniyor.")
    has_text = await session.scalar(
        select(func.count()).select_from(Transcript).where(Transcript.call_id == call_id)
    )
    if not has_text and not call.audio_path:
        raise NoTranscriptError("Çağrının transkripti ve ses kaydı yok.")
    await set_state(session, call_id, "beklemede")
    return "analysis" if has_text else "stt"


async def get_status(session: AsyncSession, call_id: UUID) -> CallStatus:
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")
    version = await session.scalar(
        select(func.max(AnalysisRow.version)).where(AnalysisRow.call_id == call_id)
    )
    return CallStatus(
        call_id=call_id,
        state=call.state,
        analysis_version=version,
        error=call.error,
        updated_at=call.updated_at,
    )


async def _load_context(session: AsyncSession, call_id: UUID) -> AnalysisContext:
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")
    rows = (
        await session.execute(
            select(TranscriptSegment)
            .join(Transcript, Transcript.id == TranscriptSegment.transcript_id)
            .where(Transcript.call_id == call_id)
            .order_by(TranscriptSegment.segment_index)
        )
    ).scalars()
    segments = [
        Segment(
            idx=r.segment_index,
            speaker="rep" if r.speaker == "rep" else "customer",
            start_ms=r.start_ms or 0,
            end_ms=r.end_ms or r.start_ms or 0,
            # Maskeli metin yoksa ham metne DÜŞÜLMEZ: LLM'e kişisel veri gitmesin.
            text_masked=r.masked_text if r.masked_text is not None else mask_text(r.text),
        )
        for r in rows
    ]
    info = CallInfo(
        started_at=call.started_at,
        answer_delay_s=call.answer_delay_s,
        duration_s=call.duration_s,
        outcome=call.switchboard_outcome,
    )
    return AnalysisContext(call_id=call_id, segments=segments, call_info=info)


async def run_call_analysis(
    call_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    orchestrator: AnalysisRunner | None = None,
) -> CallState:
    """Çağrıyı analiz eder, sonucu yazar ve nihai durumu döner.

    Hatalar çağrının durumuna yazılır, fırlatılmaz.

    `orchestrator` verilmezse varsayılan akış kurulur (LLM ayarları ortamdan okunur).
    """
    async with session_factory() as session, session.begin():
        ctx = await _load_context(session, call_id)
        if not ctx.segments:
            await set_state(session, call_id, "basarisiz", "Transkript boş.")
            return "basarisiz"
        await set_state(session, call_id, "isleniyor")

    try:
        if orchestrator is None:
            from app.agents.registry import build_default_orchestrator

            orchestrator = build_default_orchestrator()
        outcome = await orchestrator.run(ctx)
        analysis = outcome.to_analysis_result()
        error = (
            "; ".join(f"{agent}: {msg}" for agent, msg in analysis.errors.items())
            if analysis.status == "basarisiz"
            else None
        )
        async with session_factory() as session, session.begin():
            await save_analysis(session, analysis)
            await set_state(session, call_id, analysis.status, error)
        log.info("call.analyzed", call_id=str(call_id), status=analysis.status)
        return analysis.status
    except Exception as exc:
        # Beklenmeyen hata (ör. yapılandırma, veritabanı): çağrı "isleniyor"da asılı kalmasın.
        log.exception("call.analysis_crashed", call_id=str(call_id))
        async with session_factory() as session, session.begin():
            await set_state(session, call_id, "basarisiz", f"{type(exc).__name__}: {exc}"[:500])
        return "basarisiz"

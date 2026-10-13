"""Analiz sonuçlarının veritabanına yazılması ve okunması (#47).

- `save_transcript`: çağrının transkripti ve konuşmacı segmentleri (yeniden yazılabilir).
- `save_analysis`: birleşik analiz sonucu (`analysis_results`) ve her agent'ın kaydı (`agent_runs`).
  Yeniden analiz aynı çağrı için yeni sürüm satırı ekler; eskisi silinmez.
- `get_latest_analysis`: en son sürümü API şemasına (`AnalysisOut`) çevirir (#51 bunu kullanır).
- `DbRunRecorder`: orkestratörün `RunRecorder` arayüzünün veritabanı uygulaması.

Oturum yönetimi (commit/rollback) çağıranındır; bu modül yalnızca `flush` eder. Bir çağrı için
iki analiz aynı anda yazılırsa `calls` satırı kilitlenerek sürüm numaraları çakışmadan sıralanır.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.base import Segment
from app.agents.names import CRM_EXTRACTION
from app.agents.orchestrator import OrchestrationResult
from app.db.models.ai import AgentRun as AgentRunRow
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call, Transcript, TranscriptSegment
from app.schemas.analysis import (
    AgentRun,
    AnalysisResult,
    CallClassification,
    CallSummary,
    CrmExtraction,
    SalesAnalysis,
)
from app.schemas.api import AnalysisOut

log = structlog.get_logger(__name__)


class CallNotFoundError(LookupError):
    """Yazılmak istenen çağrı `calls` tablosunda yok."""


# --- Dönüşümler (saf fonksiyonlar; veritabanı gerektirmez) ----------------------------------


def analysis_row_values(result: AnalysisResult) -> dict[str, Any]:
    """Birleşik sonucu `analysis_results` sütunlarına açar. Başarısız agent'ın sütunları None."""
    values: dict[str, Any] = {
        "call_id": result.call_id,
        "status": result.status,
        "errors": result.errors,
    }
    if c := result.classification:
        values |= {
            "call_type": c.call_type.value,
            "call_type_confidence": c.confidence,
            "call_type_reason": c.reason,
        }
    if crm := result.crm:
        values |= {
            "request_category": crm.request_category.value if crm.request_category else None,
            "location": crm.location,
            "problem": crm.problem,
            "service_mode": crm.service_mode.value if crm.service_mode else None,
            "urgency": crm.urgency.value if crm.urgency else None,
            "potential_job": crm.potential_job,
            "next_action": crm.next_action.value if crm.next_action else None,
            "crm_evidence": crm.evidence,
        }
    if s := result.sales:
        values |= {
            "sales_outcome": s.outcome.value,
            "loss_reason": s.loss_reason.value if s.loss_reason else None,
            "sales_evidence": s.evidence,
            "sales_confidence": s.confidence,
        }
    if summary := result.summary:
        values |= {"summary": summary.summary, "key_points": summary.key_points}
    return values


def run_row_values(run: AgentRun, analysis_id: UUID) -> dict[str, Any]:
    return {
        "analysis_id": analysis_id,
        "agent_name": run.agent,
        "status": run.status,
        "attempts": run.attempts,
        "latency_ms": run.latency_ms,
        "error": run.error,
        "error_kind": run.error_kind,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
    }


def analysis_from_rows(row: AnalysisRow, runs: Sequence[AgentRunRow]) -> AnalysisOut:
    """Satırları API şemasına çevirir. Sütunlar boşsa ilgili agent çıktısı `None` olur."""
    classification = (
        CallClassification.model_validate(
            {
                "call_type": row.call_type,
                "confidence": row.call_type_confidence,
                "reason": row.call_type_reason or "",
            }
        )
        if row.call_type is not None and row.call_type_confidence is not None
        else None
    )
    # CRM agent çalışıp hiçbir alan bulamadıysa sonuç "tümü boş" bir CrmExtraction'dır;
    # yalnızca agent başarısız olduysa (errors'ta varsa) None döner.
    crm = (
        None
        if CRM_EXTRACTION in row.errors
        else CrmExtraction.model_validate(
            {
                "request_category": row.request_category,
                "location": row.location,
                "problem": row.problem,
                "service_mode": row.service_mode,
                "urgency": row.urgency,
                "potential_job": row.potential_job,
                "next_action": row.next_action,
                "evidence": row.crm_evidence,
            }
        )
    )
    sales = (
        SalesAnalysis.model_validate(
            {
                "outcome": row.sales_outcome,
                "loss_reason": row.loss_reason,
                "evidence": row.sales_evidence,
                "confidence": row.sales_confidence if row.sales_confidence is not None else 0,
            }
        )
        if row.sales_outcome is not None
        else None
    )
    summary = (
        CallSummary.model_validate({"summary": row.summary, "key_points": row.key_points})
        if row.summary
        else None
    )
    return AnalysisOut(
        version=row.version,
        status=row.status,
        created_at=row.created_at,
        classification=classification,
        crm=crm,
        sales=sales,
        summary=summary,
        errors=row.errors,
        runs=[
            AgentRun.model_validate(
                {
                    "agent": r.agent_name,
                    "status": r.status,
                    "attempts": r.attempts,
                    "latency_ms": r.latency_ms or 0,
                    "error": r.error,
                    "error_kind": r.error_kind,
                    "model": r.model,
                    "prompt_version": r.prompt_version,
                    "tokens_in": r.tokens_in,
                    "tokens_out": r.tokens_out,
                }
            )
            for r in runs
        ],
    )


# --- Yazma ----------------------------------------------------------------------------------


async def save_transcript(
    session: AsyncSession,
    call_id: UUID,
    segments: Sequence[Segment],
    *,
    raw_texts: Sequence[str] | None = None,
) -> UUID:
    """Çağrının transkriptini yazar; varsa eskisini (ve segmentlerini) yenisiyle değiştirir.

    `segments` maskelenmiş metni taşır (LLM ve arama yalnızca bunu görür). `raw_texts`, aynı
    sırada ham metinlerdir; verilmezse ham metin alanına da maskeli metin yazılır.
    `unknown` konuşmacı veritabanında yoktur (customer/rep); `customer` olarak kaydedilir.
    """
    if raw_texts is not None and len(raw_texts) != len(segments):
        raise ValueError("raw_texts ile segments aynı uzunlukta olmalı.")
    if await session.get(Call, call_id) is None:
        raise CallNotFoundError(str(call_id))

    masked = "\n".join(s.text_masked for s in segments)
    full = "\n".join(raw_texts) if raw_texts is not None else masked

    stmt = (
        pg_insert(Transcript)
        .values(call_id=call_id, full_text=full, masked_text=masked)
        .on_conflict_do_update(
            constraint="uq_transcripts_call_id",
            set_={"full_text": full, "masked_text": masked},
        )
        .returning(Transcript.id)
    )
    transcript_id: UUID = (await session.execute(stmt)).scalar_one()

    await session.execute(
        delete(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript_id)
    )
    for i, seg in enumerate(segments):
        if seg.speaker == "unknown":
            log.warning("transcript.unknown_speaker", call_id=str(call_id), idx=seg.idx)
        session.add(
            TranscriptSegment(
                transcript_id=transcript_id,
                segment_index=i,
                speaker="rep" if seg.speaker == "rep" else "customer",
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=raw_texts[i] if raw_texts is not None else seg.text_masked,
                masked_text=seg.text_masked,
            )
        )
    await session.flush()
    return transcript_id


async def save_analysis(session: AsyncSession, result: AnalysisResult) -> int:
    """Analizi yeni sürüm olarak yazar ve sürüm numarasını döner (commit çağıranındır)."""
    # Aynı çağrıya eşzamanlı yazımlarda sürüm numaraları çakışmasın diye çağrı satırı kilitlenir.
    locked = await session.execute(
        select(Call.id).where(Call.id == result.call_id).with_for_update()
    )
    if locked.scalar_one_or_none() is None:
        raise CallNotFoundError(str(result.call_id))

    last = await session.execute(
        select(AnalysisRow.version)
        .where(AnalysisRow.call_id == result.call_id)
        .order_by(AnalysisRow.version.desc())
        .limit(1)
    )
    version = (last.scalar_one_or_none() or 0) + 1

    row = AnalysisRow(version=version, **analysis_row_values(result))
    session.add(row)
    await session.flush()
    for run in result.runs:
        session.add(AgentRunRow(**run_row_values(run, row.id)))
    await session.flush()
    log.info("analysis.saved", call_id=str(result.call_id), version=version, status=result.status)
    return version


# --- Okuma ----------------------------------------------------------------------------------


async def get_latest_analysis(session: AsyncSession, call_id: UUID) -> AnalysisOut | None:
    """Çağrının en son analiz sürümü; hiç analiz yoksa None."""
    row = (
        await session.execute(
            select(AnalysisRow)
            .where(AnalysisRow.call_id == call_id)
            .order_by(AnalysisRow.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    runs = (
        (
            await session.execute(
                select(AgentRunRow)
                .where(AgentRunRow.analysis_id == row.id)
                .order_by(AgentRunRow.created_at, AgentRunRow.agent_name)
            )
        )
        .scalars()
        .all()
    )
    return analysis_from_rows(row, runs)


# --- Orkestratör kayıtçısı -------------------------------------------------------------------


class DbRunRecorder:
    """`RunRecorder` uygulaması: orkestratör bitince sonucu kendi oturumunda yazıp commit eder."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, result: OrchestrationResult) -> None:
        async with self._session_factory() as session, session.begin():
            await save_analysis(session, result.to_analysis_result())

"""Çağrı ve CRM okuma servisleri (#51): liste, tekil çağrı detayı ve CRM önerileri.

Kurallar:
- SQL sorguları tek bir en son analiz sürümüyle (`max(version)`) birleştirilir.
- Filtreler (tarih aralığı, aciliyet, kategori, durum, serbest metin) uygulanır.
- Sayfalama `Page[T]` sözleşmesine göredir.
- Route'lar doğrudan bu servis fonksiyonlarını çağırır; servisler HTTP bilmez.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import BinaryExpression, ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.errors import NotFoundError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call, Transcript, TranscriptSegment
from app.schemas.api import (
    CallDetail,
    CallFilters,
    CallListItem,
    CrmRecordItem,
    TranscriptOut,
    TranscriptSegmentOut,
)
from app.schemas.common import Page
from app.services.analysis_store import get_latest_analysis
from app.services.masking import mask_text


def _latest_analysis_subquery() -> Any:
    """Her çağrının en son analiz sürümünü veren alt sorgu."""
    latest_version_sq = (
        select(
            AnalysisRow.call_id.label("call_id"),
            func.max(AnalysisRow.version).label("max_version"),
        )
        .group_by(AnalysisRow.call_id)
        .subquery("latest_analysis_version_sq")
    )
    return (
        select(AnalysisRow)
        .join(
            latest_version_sq,
            (AnalysisRow.call_id == latest_version_sq.c.call_id)
            & (AnalysisRow.version == latest_version_sq.c.max_version),
        )
        .subquery("latest_analysis")
    )


def _build_filter_conditions(
    filters: CallFilters, latest_analysis: Any
) -> list[ColumnElement[bool] | BinaryExpression[Any]]:
    """`CallFilters` alanlarına göre SQLAlchemy koşullarını üretir."""
    conditions: list[ColumnElement[bool] | BinaryExpression[Any]] = []

    if filters.date_from:
        start_dt = datetime.combine(filters.date_from, time.min, tzinfo=UTC)
        conditions.append(Call.started_at >= start_dt)

    if filters.date_to:
        end_dt = datetime.combine(filters.date_to, time.max, tzinfo=UTC)
        conditions.append(Call.started_at <= end_dt)

    if filters.state:
        conditions.append(Call.state == filters.state)

    if filters.call_type:
        conditions.append(latest_analysis.c.call_type == filters.call_type.value)

    if filters.urgency:
        conditions.append(latest_analysis.c.urgency == filters.urgency.value)

    if filters.request_category:
        conditions.append(latest_analysis.c.request_category == filters.request_category.value)

    if filters.q and filters.q.strip():
        term = filters.q.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        search = f"%{term}%"
        conditions.append(
            or_(
                Call.customer_name.ilike(search, escape="\\"),
                Call.boat_name.ilike(search, escape="\\"),
                Call.marina.ilike(search, escape="\\"),
            )
        )

    return conditions


async def list_calls(session: AsyncSession, filters: CallFilters) -> Page[CallListItem]:
    """Filtrelere göre sayfalı çağrı listesi döndürür (en son analiz özetiyle)."""
    latest_analysis = _latest_analysis_subquery()
    conditions = _build_filter_conditions(filters, latest_analysis)

    count_stmt: Select[Any] = (
        select(func.count(Call.id))
        .select_from(Call)
        .outerjoin(latest_analysis, Call.id == latest_analysis.c.call_id)
    )
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    total: int = (await session.scalar(count_stmt)) or 0

    query_stmt = (
        select(
            Call.id,
            Call.started_at,
            Call.duration_s,
            Call.answer_delay_s,
            Call.switchboard_outcome,
            Call.customer_name,
            Call.boat_name,
            Call.marina,
            Call.state,
            latest_analysis.c.call_type,
            latest_analysis.c.request_category,
            latest_analysis.c.urgency,
            latest_analysis.c.sales_outcome,
            latest_analysis.c.summary,
        )
        .select_from(Call)
        .outerjoin(latest_analysis, Call.id == latest_analysis.c.call_id)
    )
    if conditions:
        query_stmt = query_stmt.where(*conditions)

    query_stmt = (
        query_stmt.order_by(Call.started_at.desc(), Call.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )

    rows: Sequence[Any] = (await session.execute(query_stmt)).all()

    items = [
        CallListItem(
            id=r[0],
            started_at=r[1],
            duration_s=r[2],
            answer_delay_s=r[3],
            switchboard_outcome=r[4],
            customer_name=r[5],
            boat_name=r[6],
            marina=r[7],
            state=r[8],
            call_type=r[9],
            request_category=r[10],
            urgency=r[11],
            sales_outcome=r[12],
            summary=r[13],
        )
        for r in rows
    ]

    return Page[CallListItem](
        items=items,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


async def get_call_detail(session: AsyncSession, call_id: UUID) -> CallDetail:
    """Çağrı, maskelenmiş transkript (segmentleriyle) ve en son analizi döndürür."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")

    transcript_row = (
        await session.execute(select(Transcript).where(Transcript.call_id == call_id))
    ).scalar_one_or_none()

    transcript_out: TranscriptOut | None = None
    if transcript_row is not None:
        segments = (
            (
                await session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_id == transcript_row.id)
                    .order_by(TranscriptSegment.segment_index)
                )
            )
            .scalars()
            .all()
        )

        transcript_out = TranscriptOut(
            text=(
                transcript_row.masked_text
                if transcript_row.masked_text is not None
                else mask_text(transcript_row.full_text)
            ),
            segments=[
                TranscriptSegmentOut(
                    index=seg.segment_index,
                    speaker=seg.speaker,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    text=seg.masked_text if seg.masked_text is not None else mask_text(seg.text),
                )
                for seg in segments
            ],
        )

    analysis_out = await get_latest_analysis(session, call_id)

    return CallDetail(
        id=call.id,
        started_at=call.started_at,
        duration_s=call.duration_s,
        answer_delay_s=call.answer_delay_s,
        switchboard_outcome=call.switchboard_outcome,
        customer_id=call.customer_id,
        boat_id=call.boat_id,
        customer_name=call.customer_name,
        customer_phone=call.customer_phone,
        boat_name=call.boat_name,
        boat_model=call.boat_model,
        marina=call.marina,
        has_audio=bool(call.audio_path),
        state=call.state,
        error=call.error,
        transcript=transcript_out,
        analysis=analysis_out,
    )


async def list_crm_records(session: AsyncSession, filters: CallFilters) -> Page[CrmRecordItem]:
    """Analiz edilmiş çağrılardan çıkarılan CRM önerilerini sayfalı olarak döndürür."""
    latest_analysis = _latest_analysis_subquery()
    conditions = _build_filter_conditions(filters, latest_analysis)

    count_stmt: Select[Any] = (
        select(func.count(Call.id))
        .select_from(Call)
        .join(latest_analysis, Call.id == latest_analysis.c.call_id)
    )
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    total: int = (await session.scalar(count_stmt)) or 0

    query_stmt = (
        select(
            Call.id,
            Call.started_at,
            Call.customer_name,
            Call.boat_name,
            latest_analysis.c.version,
            latest_analysis.c.request_category,
            latest_analysis.c.location,
            latest_analysis.c.problem,
            latest_analysis.c.service_mode,
            latest_analysis.c.urgency,
            latest_analysis.c.potential_job,
            latest_analysis.c.next_action,
            latest_analysis.c.crm_evidence,
        )
        .select_from(Call)
        .join(latest_analysis, Call.id == latest_analysis.c.call_id)
    )
    if conditions:
        query_stmt = query_stmt.where(*conditions)

    query_stmt = (
        query_stmt.order_by(Call.started_at.desc(), Call.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )

    rows: Sequence[Any] = (await session.execute(query_stmt)).all()

    items = [
        CrmRecordItem(
            call_id=r[0],
            started_at=r[1],
            customer_name=r[2],
            boat_name=r[3],
            analysis_version=r[4],
            request_category=r[5],
            location=r[6],
            problem=r[7],
            service_mode=r[8],
            urgency=r[9],
            potential_job=r[10],
            next_action=r[11],
            evidence=r[12] or {},
        )
        for r in rows
    ]

    return Page[CrmRecordItem](
        items=items,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )

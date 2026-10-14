"""KPI ve çağrı analitiği hesaplama servisi (#52).

Kurallar:
- Çağrı ve satış analitiği istatistikleri doğrudan PostgreSQL SQL toplamalarıyla
  hesaplanır (LLM kullanılmaz).
- Her çağrının yalnızca en son analiz sürümü (`max(version)`) dikkate alınır.
- Dönemdeki her gün için `daily_calls` üretilir (çağrı olmayan günler 0 döner).
- Veri olmadığında sıfır/boş değerler döner, hata vermez.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call
from app.domain.enums import CallType, LossReason, RequestCategory, SalesOutcomeType, Urgency
from app.schemas.analysis import CountItem, DailyCount, KpiSummary
from app.schemas.api import PeriodFilter

MAX_PERIOD_DAYS = 366


def _resolve_period(filter_params: PeriodFilter) -> tuple[date, date]:
    """Sorgu parametrelerine göre dönem başlangıç ve bitiş tarihlerini belirler.

    Her ikisi de boşsa son 30 gün alınır. Dönem en fazla `MAX_PERIOD_DAYS` gün olabilir
    (günlük liste her gün için bir satır üretir).
    """
    period_start, period_end = _raw_period(filter_params)
    if (period_end - period_start).days >= MAX_PERIOD_DAYS:
        raise AppError(f"Dönem en fazla {MAX_PERIOD_DAYS} gün olabilir.")
    return period_start, period_end


def _raw_period(filter_params: PeriodFilter) -> tuple[date, date]:
    today = datetime.now(UTC).date()

    if filter_params.date_from and filter_params.date_to:
        return filter_params.date_from, filter_params.date_to

    if filter_params.date_to and not filter_params.date_from:
        period_end = filter_params.date_to
        period_start = period_end - timedelta(days=29)
        return period_start, period_end

    if filter_params.date_from and not filter_params.date_to:
        period_start = filter_params.date_from
        period_end = max(today, period_start + timedelta(days=29))
        return period_start, period_end

    period_end = today
    period_start = period_end - timedelta(days=29)
    return period_start, period_end


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


async def get_kpi_summary(session: AsyncSession, filter_params: PeriodFilter) -> KpiSummary:
    """Dönem için KPI metriklerini ve dağılım grafiklerini hesaplar."""
    period_start, period_end = _resolve_period(filter_params)

    start_dt = datetime.combine(period_start, time.min, tzinfo=UTC)
    end_dt = datetime.combine(period_end, time.max, tzinfo=UTC)
    period_condition = (Call.started_at >= start_dt) & (Call.started_at <= end_dt)

    latest_analysis = _latest_analysis_subquery()

    # 1. Ana KPI metrikleri (tek SQL sorgusu)
    summary_stmt = (
        select(
            func.count(Call.id).label("total_calls"),
            func.count(latest_analysis.c.id)
            .filter(latest_analysis.c.status.in_(["tamam", "kismi"]))
            .label("analyzed_calls"),
            func.count(latest_analysis.c.id)
            .filter(latest_analysis.c.call_type == CallType.YENI_MUSTERI.value)
            .label("new_customers"),
            func.count(latest_analysis.c.id)
            .filter(latest_analysis.c.call_type == CallType.SERVIS.value)
            .label("service_requests"),
            func.count(latest_analysis.c.id)
            .filter(latest_analysis.c.call_type == CallType.TEKLIF.value)
            .label("quote_requests"),
            func.count(latest_analysis.c.id)
            .filter(latest_analysis.c.call_type == CallType.ACIL.value)
            .label("urgent_requests"),
            func.count(latest_analysis.c.id)
            .filter(latest_analysis.c.sales_outcome == SalesOutcomeType.SATISA_DONUSTU.value)
            .label("converted_sales"),
            func.avg(Call.answer_delay_s).label("avg_delay"),
        )
        .select_from(Call)
        .outerjoin(latest_analysis, Call.id == latest_analysis.c.call_id)
        .where(period_condition)
    )
    summary_row = (await session.execute(summary_stmt)).one()

    total_calls: int = summary_row[0] or 0
    analyzed_calls: int = summary_row[1] or 0
    new_customers: int = summary_row[2] or 0
    service_requests: int = summary_row[3] or 0
    quote_requests: int = summary_row[4] or 0
    urgent_requests: int = summary_row[5] or 0
    converted_sales: int = summary_row[6] or 0
    raw_avg_delay: float | None = summary_row[7]

    conversion_rate: float | None = (
        round(converted_sales / analyzed_calls, 3) if analyzed_calls > 0 else None
    )
    avg_answer_delay_s: float | None = (
        round(float(raw_avg_delay), 1) if raw_avg_delay is not None else None
    )

    # 2. Kaybedilme nedenleri dağılımı
    loss_stmt = (
        select(
            latest_analysis.c.loss_reason,
            func.count(latest_analysis.c.id),
        )
        .select_from(Call)
        .join(latest_analysis, Call.id == latest_analysis.c.call_id)
        .where(
            period_condition,
            latest_analysis.c.sales_outcome == SalesOutcomeType.KAYBEDILDI.value,
            latest_analysis.c.loss_reason.isnot(None),
        )
        .group_by(latest_analysis.c.loss_reason)
        .order_by(func.count(latest_analysis.c.id).desc())
    )
    loss_rows: Sequence[Any] = (await session.execute(loss_stmt)).all()
    lost_by_reason: dict[LossReason, int] = {
        LossReason(r[0]): r[1] for r in loss_rows if r[0] is not None
    }

    # 3. Kategoriye göre dağılım
    cat_stmt = (
        select(
            latest_analysis.c.request_category,
            func.count(latest_analysis.c.id),
        )
        .select_from(Call)
        .join(latest_analysis, Call.id == latest_analysis.c.call_id)
        .where(
            period_condition,
            latest_analysis.c.request_category.isnot(None),
        )
        .group_by(latest_analysis.c.request_category)
        .order_by(func.count(latest_analysis.c.id).desc())
    )
    cat_rows: Sequence[Any] = (await session.execute(cat_stmt)).all()
    by_category: dict[RequestCategory, int] = {
        RequestCategory(r[0]): r[1] for r in cat_rows if r[0] is not None
    }

    # 4. Aciliyete göre dağılım
    urg_stmt = (
        select(
            latest_analysis.c.urgency,
            func.count(latest_analysis.c.id),
        )
        .select_from(Call)
        .join(latest_analysis, Call.id == latest_analysis.c.call_id)
        .where(
            period_condition,
            latest_analysis.c.urgency.isnot(None),
        )
        .group_by(latest_analysis.c.urgency)
        .order_by(func.count(latest_analysis.c.id).desc())
    )
    urg_rows: Sequence[Any] = (await session.execute(urg_stmt)).all()
    by_urgency: dict[Urgency, int] = {Urgency(r[0]): r[1] for r in urg_rows if r[0] is not None}

    # 5. En sık arızalar (top problems, ilk 10)
    prob_stmt = (
        select(
            latest_analysis.c.problem,
            func.count(latest_analysis.c.id),
        )
        .select_from(Call)
        .join(latest_analysis, Call.id == latest_analysis.c.call_id)
        .where(
            period_condition,
            latest_analysis.c.problem.isnot(None),
            func.trim(latest_analysis.c.problem) != "",
        )
        .group_by(latest_analysis.c.problem)
        .order_by(func.count(latest_analysis.c.id).desc(), latest_analysis.c.problem)
        .limit(10)
    )
    prob_rows: Sequence[Any] = (await session.execute(prob_stmt)).all()
    top_problems: list[CountItem] = [CountItem(name=r[0], count=r[1]) for r in prob_rows]

    # 6. En yoğun marinalar (ilk 10)
    marina_stmt = (
        select(
            Call.marina,
            func.count(Call.id),
        )
        .select_from(Call)
        .where(
            period_condition,
            Call.marina.isnot(None),
            func.trim(Call.marina) != "",
        )
        .group_by(Call.marina)
        .order_by(func.count(Call.id).desc(), Call.marina)
        .limit(10)
    )
    marina_rows: Sequence[Any] = (await session.execute(marina_stmt)).all()
    busiest_marinas: list[CountItem] = [CountItem(name=r[0], count=r[1]) for r in marina_rows]

    # 7. Günlük çağrı dağılımı (dönemdeki her gün için; boş gün 0)
    day_col = func.date(func.timezone("UTC", Call.started_at))
    daily_stmt = (
        select(
            day_col.label("day"),
            func.count(Call.id).label("count"),
        )
        .select_from(Call)
        .where(period_condition)
        .group_by(day_col)
        .order_by(day_col)
    )
    daily_rows: Sequence[Any] = (await session.execute(daily_stmt)).all()
    daily_map: dict[date, int] = {r[0]: r[1] for r in daily_rows}

    daily_calls: list[DailyCount] = []
    curr_day = period_start
    while curr_day <= period_end:
        daily_calls.append(DailyCount(day=curr_day, count=daily_map.get(curr_day, 0)))
        curr_day += timedelta(days=1)

    return KpiSummary(
        period_start=period_start,
        period_end=period_end,
        total_calls=total_calls,
        analyzed_calls=analyzed_calls,
        new_customers=new_customers,
        service_requests=service_requests,
        quote_requests=quote_requests,
        urgent_requests=urgent_requests,
        converted_sales=converted_sales,
        conversion_rate=conversion_rate,
        lost_by_reason=lost_by_reason,
        top_problems=top_problems,
        busiest_marinas=busiest_marinas,
        by_category=by_category,
        by_urgency=by_urgency,
        daily_calls=daily_calls,
        avg_answer_delay_s=avg_answer_delay_s,
    )

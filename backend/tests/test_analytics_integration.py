"""KPI ve çağrı analitiği hesaplama entegrasyon testleri (#52).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Seed verisindeki sayıların elle doğrulanması, boş veri durumu ve çoklu sürüm testi.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.domain.enums import LossReason, RequestCategory, Urgency
from app.schemas.api import PeriodFilter
from app.services.analytics_service import get_kpi_summary

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def factory(conn: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


async def test_seed_kpi_counts_verified_by_hand(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Seed verisindeki 30 çağrının KPI değerlerinin doğrulanması (#52 bitiş kriteri)."""
    async with factory() as session:
        summary = await get_kpi_summary(
            session,
            PeriodFilter(date_from=date(2026, 10, 5), date_to=date(2026, 10, 13)),
        )

        assert summary.period_start == date(2026, 10, 5)
        assert summary.period_end == date(2026, 10, 13)
        assert summary.total_calls == 30
        assert summary.analyzed_calls == 30

        # Çağrı tipi sayıları (toplam 30 çağrı: 4 yeni, 11 servis, 6 teklif, 4 acil, 5 bilgi)
        assert summary.new_customers == 4
        assert summary.service_requests == 11
        assert summary.quote_requests == 6
        assert summary.urgent_requests == 4

        # Satış dönüşümü: 10 satisa_donustu / 30 analiz = 0.333
        assert summary.converted_sales == 10
        assert summary.conversion_rate == 0.333

        # Kaybedilme nedenleri (11 kaybedildi: fiyat 3, takvim 2, geç dönüş 2, rakip 2, vb.)
        assert summary.lost_by_reason[LossReason.FIYAT] == 3
        assert summary.lost_by_reason[LossReason.TAKVIM] == 2
        assert summary.lost_by_reason[LossReason.GEC_DONUS] == 2
        assert summary.lost_by_reason[LossReason.RAKIP] == 2
        assert summary.lost_by_reason[LossReason.DIGER] == 1
        assert summary.lost_by_reason[LossReason.GUVEN] == 1
        assert sum(summary.lost_by_reason.values()) == 11

        # Kategori sayıları (makine en çok: 10)
        assert summary.by_category[RequestCategory.MAKINE] == 10
        assert summary.by_category[RequestCategory.ELEKTRIK_ELEKTRONIK] == 5

        # Aciliyet sayıları
        assert summary.by_urgency[Urgency.DUSUK] == 14
        assert summary.by_urgency[Urgency.NORMAL] == 9
        assert summary.by_urgency[Urgency.ACIL] == 4
        assert summary.by_urgency[Urgency.YUKSEK] == 3
        assert sum(summary.by_urgency.values()) == 30

        # Ortalama cevap süresi (santral bilgisi ortalaması: 11.0 sn)
        assert summary.avg_answer_delay_s == 11.0

        # En sık arızalar ve en yoğun marinalar
        assert len(summary.top_problems) > 0
        assert len(summary.busiest_marinas) > 0

        # Günlük çağrılar: 5-13 Ekim arası 9 günün hepsi mevcut ve toplam çağrı sayısı 30
        assert len(summary.daily_calls) == 9
        assert sum(d.count for d in summary.daily_calls) == 30
        assert summary.daily_calls[0].day == date(2026, 10, 5)
        assert summary.daily_calls[-1].day == date(2026, 10, 13)


async def test_empty_data_does_not_error(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Veritabanında hiç çağrı olmayan bir dönemde hata vermeden sıfır/boş dönmeli."""
    async with factory() as session:
        summary = await get_kpi_summary(
            session,
            PeriodFilter(date_from=date(2020, 1, 1), date_to=date(2020, 1, 7)),
        )

        assert summary.total_calls == 0
        assert summary.analyzed_calls == 0
        assert summary.new_customers == 0
        assert summary.service_requests == 0
        assert summary.quote_requests == 0
        assert summary.urgent_requests == 0
        assert summary.converted_sales == 0
        assert summary.conversion_rate is None
        assert summary.lost_by_reason == {}
        assert summary.top_problems == []
        assert summary.busiest_marinas == []
        assert summary.by_category == {}
        assert summary.by_urgency == {}
        assert summary.avg_answer_delay_s is None

        # 7 günün hepsi 0 sayısıyla listede yer almalı
        assert len(summary.daily_calls) == 7
        assert all(d.count == 0 for d in summary.daily_calls)


async def test_kpi_picks_latest_analysis_version_only(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Bir çağrı yeniden analiz edildiğinde eski sürümün KPI sayılarına etkisi kalmamalı."""
    test_day = date(2025, 6, 15)
    test_dt = datetime(2025, 6, 15, 12, 0, tzinfo=UTC)

    call_res = await conn.execute(
        text(
            "INSERT INTO calls (started_at, duration_s, answer_delay_s, state) "
            "VALUES (:t, 120, 10, 'tamam') RETURNING id"
        ),
        {"t": test_dt},
    )
    call_id: UUID = call_res.scalar_one()

    # Sürüm 1: kaybedildi (fiyat)
    await conn.execute(
        text(
            "INSERT INTO analysis_results "
            "(call_id, version, status, call_type, sales_outcome, loss_reason) "
            "VALUES (:cid, 1, 'tamam', 'teklif', 'kaybedildi', 'fiyat')"
        ),
        {"cid": call_id},
    )

    # Sürüm 2: satisa_donustu (yeni sürüm)
    await conn.execute(
        text(
            "INSERT INTO analysis_results "
            "(call_id, version, status, call_type, sales_outcome, loss_reason) "
            "VALUES (:cid, 2, 'tamam', 'servis', 'satisa_donustu', NULL)"
        ),
        {"cid": call_id},
    )

    async with factory() as session:
        summary = await get_kpi_summary(session, PeriodFilter(date_from=test_day, date_to=test_day))

        assert summary.total_calls == 1
        assert summary.analyzed_calls == 1
        assert summary.service_requests == 1
        assert summary.quote_requests == 0
        assert summary.converted_sales == 1
        assert summary.conversion_rate == 1.0
        assert summary.lost_by_reason == {}

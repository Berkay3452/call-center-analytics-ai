"""Çağrı ve CRM okuma servisleri, gerçek PostgreSQL üzerinde (#51).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Seed verisiyle okuma, çoklu analiz sürümlerinde yalnızca en son sürümün alınması,
filtreleme (tarih, aciliyet, kategori, durum, serbest metin) ve sayfalama davranışını test eder.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.models.ai import Call
from app.domain.enums import LossReason, RequestCategory, SalesOutcomeType, Urgency
from app.schemas.api import CallFilters
from app.services.call_reader import get_call_detail, list_calls, list_crm_records

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


async def test_list_calls_with_seed_data(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        calls_page = await list_calls(session, CallFilters(page=1, page_size=10))
        assert calls_page.total >= 10
        assert len(calls_page.items) == 10
        assert calls_page.page == 1
        assert calls_page.page_size == 10

        # Tarihe göre azalan sırada olduğunu doğrula
        for i in range(len(calls_page.items) - 1):
            assert calls_page.items[i].started_at >= calls_page.items[i + 1].started_at


async def test_list_calls_filters(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        # Aciliyet filtresi
        filtered_urgency = await list_calls(
            session, CallFilters(urgency=Urgency.YUKSEK, page_size=50)
        )
        assert filtered_urgency.total > 0
        for item in filtered_urgency.items:
            assert item.urgency == Urgency.YUKSEK

        # Kategori filtresi
        filtered_cat = await list_calls(
            session, CallFilters(request_category=RequestCategory.MAKINE, page_size=50)
        )
        assert filtered_cat.total > 0
        for item in filtered_cat.items:
            assert item.request_category == RequestCategory.MAKINE

        # Serbest metin arama
        searched = await list_calls(session, CallFilters(q="Rüzgar"))
        assert searched.total > 0
        for item in searched.items:
            assert (
                "rüzgar" in (item.boat_name or "").lower()
                or "rüzgar" in (item.customer_name or "").lower()
                or "rüzgar" in (item.marina or "").lower()
            )


async def test_get_call_detail_with_transcript_and_analysis(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        # Seed çağrılarından birini bul
        call_id = await session.scalar(
            select(Call.id).where(Call.customer_name == "Burak Çelik").limit(1)
        )
        assert call_id is not None

        detail = await get_call_detail(session, call_id)
        assert detail.id == call_id
        assert detail.customer_name == "Burak Çelik"
        assert detail.transcript is not None
        assert len(detail.transcript.segments) > 0
        assert detail.analysis is not None
        assert detail.analysis.classification is not None
        assert detail.analysis.crm is not None


async def test_get_call_detail_not_found(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        with pytest.raises(NotFoundError, match="Çağrı bulunamadı"):
            await get_call_detail(session, UUID("00000000-0000-0000-0000-000000000099"))


async def test_list_crm_records_with_seed_data(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        crm_page = await list_crm_records(session, CallFilters(page=1, page_size=10))
        assert crm_page.total >= 10
        assert len(crm_page.items) == 10

        first = crm_page.items[0]
        assert first.call_id is not None
        assert first.analysis_version >= 1
        assert first.request_category is not None


async def test_latest_analysis_version_is_picked_when_multiple_exist(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Yeniden analiz yapıldığında liste ve CRM yalnızca son sürümü döner."""
    now = datetime.now(UTC)
    call_id_res = await conn.execute(
        text(
            "INSERT INTO calls (started_at, customer_name, boat_name, marina, state) "
            "VALUES (:t, 'Test Müşteri', 'Test Tekne', 'Test Marina', 'tamam') "
            "RETURNING id"
        ),
        {"t": now},
    )
    call_id: UUID = call_id_res.scalar_one()

    # Sürüm 1
    await conn.execute(
        text(
            "INSERT INTO analysis_results "
            "(call_id, version, status, request_category, urgency, summary) "
            "VALUES (:cid, 1, 'tamam', 'diger', 'dusuk', 'Eski özet v1')"
        ),
        {"cid": call_id},
    )

    # Sürüm 2 (en güncel)
    await conn.execute(
        text(
            "INSERT INTO analysis_results "
            "(call_id, version, status, request_category, urgency, summary) "
            "VALUES (:cid, 2, 'tamam', 'makine', 'yuksek', 'Yeni özet v2')"
        ),
        {"cid": call_id},
    )

    async with factory() as session:
        res = await list_calls(session, CallFilters(q="Test Müşteri"))
        assert res.total == 1
        item = res.items[0]
        assert item.id == call_id
        assert item.request_category == RequestCategory.MAKINE
        assert item.urgency == Urgency.YUKSEK
        assert item.summary == "Yeni özet v2"

        crm_res = await list_crm_records(session, CallFilters(q="Test Müşteri"))
        assert crm_res.total == 1
        crm_item = crm_res.items[0]
        assert crm_item.analysis_version == 2
        assert crm_item.request_category == RequestCategory.MAKINE
        assert crm_item.urgency == Urgency.YUKSEK


async def test_free_text_wildcards_are_literal(factory: async_sessionmaker[AsyncSession]) -> None:
    """`%` ve `_` joker değil, düz karakter olarak aranır."""
    async with factory() as session:
        page = await list_calls(session, CallFilters(q="%"))
        assert page.total == 0
        page = await list_calls(session, CallFilters(q="_"))
        assert page.total == 0


async def test_list_calls_loss_reason_for_lost_calls(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Kaybedilen çağrılarda loss_reason dolu, diğerlerinde null gelir (#79)."""
    async with factory() as session:
        calls_page = await list_calls(session, CallFilters(page=1, page_size=100))
        assert calls_page.total >= 30

        lost_calls = [c for c in calls_page.items if c.sales_outcome == SalesOutcomeType.KAYBEDILDI]
        assert len(lost_calls) == 11
        for call in lost_calls:
            assert call.loss_reason is not None
            assert isinstance(call.loss_reason, LossReason)

        non_lost_calls = [
            c for c in calls_page.items if c.sales_outcome != SalesOutcomeType.KAYBEDILDI
        ]
        assert len(non_lost_calls) == 19
        for call in non_lost_calls:
            assert call.loss_reason is None


async def test_list_calls_and_crm_marina_filter(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """marina filtresi hem calls hem de crm için tam eşleşme yapar (#81)."""
    async with factory() as session:
        calls = await list_calls(session, CallFilters(marina="Tuzla Marina", page_size=50))
        assert calls.total == 4
        assert len(calls.items) == 4
        assert all(c.marina == "Tuzla Marina" for c in calls.items)

        crm = await list_crm_records(session, CallFilters(marina="Tuzla Marina", page_size=50))
        assert crm.total == 4
        assert len(crm.items) == 4
        assert all(r.location == "Tuzla Marina" for r in crm.items)

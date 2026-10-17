"""CRM önerisi inceleme akışı, gerçek veritabanı entegrasyon testleri (#106).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Test edilen akışlar:
1. Onay (seed çağrısı, servis emri oluşur: status='yeni_atandi', category, description)
2. Idempotent ikinci onay (tekrar onay aynı servis emrini döner, ikinci servis emri oluşturmaz)
3. Düzenlenmiş alanlarla onay (değiştirilen alanlar edited_fields'a yazılır, emirde kullanılır)
4. Red (durum 'reddedildi', note kaydedilir, servis emri oluşmaz)
5. Onay <-> red geçişi (serbest geçiş, ilk servis emri korunur)
6. Eşleşmeyen çağrıda 409 ("Müşteri/tekne eşleşmedi")
7. Yeni analiz sürümünde yeniden 'bekliyor' (inceleme analiz sürümüne bağlıdır)
8. Durum filtresi (GET /crm?status=bekliyor|onaylandi|reddedildi)
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.errors import ConflictError
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call, CrmReview
from app.db.models.external import ServiceOrder
from app.domain.enums import CrmReviewStatus, RequestCategory, ServiceOrderStatus, Urgency
from app.schemas.api import CallFilters, CrmApproveIn, CrmRejectIn
from app.services.call_reader import list_crm_records
from app.services.crm_review_service import approve_crm_record, reject_crm_record

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


async def _get_seed_call_with_analysis(session: AsyncSession) -> tuple[Call, AnalysisRow]:
    """Seed verisinden analizli ve müşteri/tekne eşleşmesi olan bir çağrı seçer."""
    stmt = (
        select(Call, AnalysisRow)
        .join(AnalysisRow, Call.id == AnalysisRow.call_id)
        .where(Call.customer_id.is_not(None), Call.boat_id.is_not(None))
        .order_by(AnalysisRow.version.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    assert row is not None, "Test için analizli ve müşteri/teknesi olan seed çağrısı bulunamadı."
    return row[0], row[1]


async def test_approve_creates_service_order_and_review(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        call, analysis = await _get_seed_call_with_analysis(session)

        # Onayla
        out = await approve_crm_record(session, call.id, CrmApproveIn(note="Test onayı"))
        assert out.status == CrmReviewStatus.ONAYLANDI
        assert out.call_id == call.id
        assert out.analysis_id == analysis.id
        assert out.service_order_id is not None
        assert out.note == "Test onayı"
        assert out.edited_fields == {}

        # Veritabanında ServiceOrder kaydını doğrula
        order = await session.get(ServiceOrder, out.service_order_id)
        assert order is not None
        assert order.status == ServiceOrderStatus.YENI_ATANDI.value
        assert order.customer_id == call.customer_id
        assert order.boat_id == call.boat_id
        assert order.category == analysis.request_category
        assert order.source_call_id == call.id


async def test_approve_is_idempotent(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        call, _ = await _get_seed_call_with_analysis(session)

        # İlk onay
        out1 = await approve_crm_record(session, call.id, CrmApproveIn())
        first_order_id = out1.service_order_id
        assert first_order_id is not None

        # İkinci onay (tekrar)
        out2 = await approve_crm_record(session, call.id, CrmApproveIn())
        assert out2.service_order_id == first_order_id

        # Bu çağrıya bağlı toplam servis emri sayısı 1 olmalı
        order_count = await session.scalar(
            select(func.count(ServiceOrder.id)).where(ServiceOrder.source_call_id == call.id)
        )
        assert order_count == 1


async def test_approve_with_edited_fields(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        call, _ = await _get_seed_call_with_analysis(session)

        approve_in = CrmApproveIn(
            request_category=RequestCategory.ELEKTRIK_ELEKTRONIK,
            problem="Aküler şarj tutmuyor",
            potential_job="Akü grubu yenileme",
            urgency=Urgency.ACIL,
            note="Müşteri talebiyle kategori düzeltildi",
        )
        out = await approve_crm_record(session, call.id, approve_in)
        assert out.status == CrmReviewStatus.ONAYLANDI
        assert out.edited_fields == {
            "request_category": "elektrik_elektronik",
            "problem": "Aküler şarj tutmuyor",
            "potential_job": "Akü grubu yenileme",
            "urgency": "acil",
        }
        assert out.note == "Müşteri talebiyle kategori düzeltildi"

        # Servis emri düzenlenen alanlara göre oluşturulmalı
        order = await session.get(ServiceOrder, out.service_order_id)
        assert order is not None
        assert order.category == "elektrik_elektronik"
        assert "Aküler şarj tutmuyor" in (order.description or "")
        assert "Akü grubu yenileme" in (order.description or "")


async def test_reject_crm_record(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        call, analysis = await _get_seed_call_with_analysis(session)

        reject_in = CrmRejectIn(note="Servis randevusu gerekmiyor, sadece bilgi verildi")
        out = await reject_crm_record(session, call.id, reject_in)
        assert out.status == CrmReviewStatus.REDDEDILDI
        assert out.call_id == call.id
        assert out.analysis_id == analysis.id
        assert out.note == "Servis randevusu gerekmiyor, sadece bilgi verildi"
        assert out.service_order_id is None

        # Veritabanında kontrol
        rev = await session.scalar(select(CrmReview).where(CrmReview.analysis_id == analysis.id))
        assert rev is not None
        assert rev.status == "reddedildi"


async def test_transition_between_approve_and_reject(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        call, _ = await _get_seed_call_with_analysis(session)

        # 1. Onayla
        out_approved = await approve_crm_record(session, call.id, CrmApproveIn())
        assert out_approved.status == CrmReviewStatus.ONAYLANDI
        order_id = out_approved.service_order_id

        # 2. Reddet
        out_rejected = await reject_crm_record(session, call.id, CrmRejectIn(note="İptal edildi"))
        assert out_rejected.status == CrmReviewStatus.REDDEDILDI

        # 3. Yeniden Onayla -> aynı servis emri döner (idempotent)
        out_reapproved = await approve_crm_record(session, call.id, CrmApproveIn())
        assert out_reapproved.status == CrmReviewStatus.ONAYLANDI
        assert out_reapproved.service_order_id == order_id


async def test_unmatched_call_returns_409(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        # Müşteri/teknesi eşleşmemiş yeni bir çağrı ve analiz oluştur
        unmatched_call = Call(
            id=uuid4(),
            started_at=datetime.now(UTC),
            customer_name="Bilinmeyen Kişi",
            customer_id=None,
            boat_id=None,
            state="tamam",
        )
        session.add(unmatched_call)
        await session.flush()

        analysis = AnalysisRow(
            id=uuid4(),
            call_id=unmatched_call.id,
            version=1,
            status="tamam",
            request_category="makine",
            problem="Arıza",
        )
        session.add(analysis)
        await session.flush()

        # Onaylamaya çalışınca 409 Conflict fırlatmalı
        with pytest.raises(ConflictError) as exc_info:
            await approve_crm_record(session, unmatched_call.id, CrmApproveIn())

        assert exc_info.value.status_code == 409
        assert "Müşteri/tekne eşleşmedi" in exc_info.value.message


async def test_reanalysis_reverts_to_bekliyor(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        call, _ = await _get_seed_call_with_analysis(session)

        # Çağrıyı onayla
        await approve_crm_record(session, call.id, CrmApproveIn())

        # Listeden kontrol et -> durum onaylandi
        page1 = await list_crm_records(session, CallFilters(status=CrmReviewStatus.ONAYLANDI))
        assert any(item.call_id == call.id for item in page1.items)

        # Yeni bir analiz sürümü (v2) ekle
        v2_analysis = AnalysisRow(
            id=uuid4(),
            call_id=call.id,
            version=99,  # yüksek bir sürüm numarası
            status="tamam",
            request_category="makine",
            problem="Yeniden analiz sonucu",
        )
        session.add(v2_analysis)
        await session.flush()

        # Yeni sürüm için durum 'bekliyor' olmalıdır
        page_waiting = await list_crm_records(session, CallFilters(status=CrmReviewStatus.BEKLIYOR))
        matching = [item for item in page_waiting.items if item.call_id == call.id]
        assert len(matching) == 1
        assert matching[0].review_status == CrmReviewStatus.BEKLIYOR
        assert matching[0].analysis_version == 99
        assert matching[0].service_order_id is None


async def test_crm_status_filter(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        # İki farklı çağrı seç
        stmt = (
            select(Call)
            .join(AnalysisRow, Call.id == AnalysisRow.call_id)
            .where(Call.customer_id.is_not(None), Call.boat_id.is_not(None))
            .limit(2)
        )
        calls = (await session.execute(stmt)).scalars().all()
        assert len(calls) >= 2
        call_a, call_b = calls[0], calls[1]

        # call_a onayla, call_b reddet
        await approve_crm_record(session, call_a.id, CrmApproveIn())
        await reject_crm_record(session, call_b.id, CrmRejectIn(note="Reddet"))

        # status=onaylandi filtresi
        onaylandi_page = await list_crm_records(
            session, CallFilters(status=CrmReviewStatus.ONAYLANDI)
        )
        assert any(item.call_id == call_a.id for item in onaylandi_page.items)
        assert all(item.call_id != call_b.id for item in onaylandi_page.items)

        # status=reddedildi filtresi
        reddedildi_page = await list_crm_records(
            session, CallFilters(status=CrmReviewStatus.REDDEDILDI)
        )
        assert any(item.call_id == call_b.id for item in reddedildi_page.items)
        assert all(item.call_id != call_a.id for item in reddedildi_page.items)

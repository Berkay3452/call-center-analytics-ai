"""Servis emirleri API uçları entegrasyon testleri (#118).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Test edilen akışlar:
1. Liste ve sayfalama (GET /service-orders)
2. Filtreler: status, date_from, date_to, marina, q (GET /service-orders)
3. Tekil servis emri detayı: müşteri, tekne, usta bilgileri (GET /service-orders/{id})
4. Kaynak çağrı ve CRM önerisi özeti (#106'dan onaylanan servis emri için)
5. Durum güncelleme geçerli iş akışı:
   yeni_atandi -> kesifte -> onaylandi -> devam_ediyor -> tamamlandi
   (tamamlandi olunca completed_at doldurulur)
6. Geçersiz durum geçişinde 400 hatası
7. Olmayan servis emrinde 404 hatası
8. Servis anahtarı doğrulama (401)
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db_session
from app.core.config import Settings
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.db.models.ai import Call
from app.db.models.external import Boat, Craftsman, Customer, ServiceOrder
from app.domain.enums import ServiceOrderStatus
from app.main import create_app
from app.schemas.api import CrmApproveIn
from app.services.crm_review_service import approve_crm_record
from tests.conftest import TEST_SERVICE_KEY, make_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


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


@pytest.fixture
async def client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(database_url=Settings().database_url))

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _get_any_seed_service_order(session: AsyncSession) -> ServiceOrder:
    order = (await session.execute(select(ServiceOrder).limit(1))).scalar_one_or_none()
    assert order is not None, "Veritabanında seed servis emri bulunamadı."
    return order


async def _create_test_order(
    session: AsyncSession,
    status: ServiceOrderStatus = ServiceOrderStatus.YENI_ATANDI,
) -> ServiceOrder:
    customer = (await session.execute(select(Customer).limit(1))).scalar_one()
    boat = (
        await session.execute(select(Boat).where(Boat.owner_id == customer.id).limit(1))
    ).scalar_one()
    craftsman = (await session.execute(select(Craftsman).limit(1))).scalar_one_or_none()

    order = ServiceOrder(
        customer_id=customer.id,
        boat_id=boat.id,
        craftsman_id=craftsman.id if craftsman else None,
        category="makine",
        description="Özel test emri",
        status=status.value,
    )
    session.add(order)
    await session.commit()
    return order


# --- Testler -----------------------------------------------------------------------------------


async def test_list_service_orders_pagination(client: AsyncClient) -> None:
    """GET /api/v1/service-orders sayfalı liste yapısını döner."""
    resp = await client.get("/api/v1/service-orders?page=1&page_size=5", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["items"]) <= 5
    assert data["total"] >= len(data["items"])

    if data["items"]:
        first = data["items"][0]
        assert "id" in first
        assert "status" in first
        assert "customer_name" in first
        assert "boat_name" in first


async def test_list_service_orders_status_filter(client: AsyncClient) -> None:
    """GET /api/v1/service-orders?status=... doğru kayıtları süzer."""
    resp = await client.get(
        f"/api/v1/service-orders?status={ServiceOrderStatus.TAMAMLANDI.value}&page_size=50",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["status"] == ServiceOrderStatus.TAMAMLANDI.value


async def test_list_service_orders_search_filter(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    """GET /api/v1/service-orders?q=... serbest metin araması yapar."""
    async with factory() as session:
        seed_order = await _get_any_seed_service_order(session)
        customer = await session.get(Customer, seed_order.customer_id)
        assert customer is not None
        search_term = customer.full_name[:4]

    resp = await client.get(f"/api/v1/service-orders?q={search_term}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(search_term.lower() in item["customer_name"].lower() for item in data["items"])


async def test_list_service_orders_date_filter(client: AsyncClient) -> None:
    """GET /api/v1/service-orders?date_from=...&date_to=... tarihe göre filtreler."""
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    resp = await client.get(
        f"/api/v1/service-orders?date_from={yesterday}&date_to={tomorrow}",
        headers=HEADERS,
    )
    assert resp.status_code == 200

    # Hatalı tarih sırası 422 döner
    invalid_resp = await client.get(
        f"/api/v1/service-orders?date_from={tomorrow}&date_to={yesterday}",
        headers=HEADERS,
    )
    assert invalid_resp.status_code == 422


async def test_get_service_order_detail_seed(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    """GET /api/v1/service-orders/{id} tekil servis emri detayını getirir."""
    async with factory() as session:
        seed_order = await _get_any_seed_service_order(session)

    resp = await client.get(f"/api/v1/service-orders/{seed_order.id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == str(seed_order.id)
    assert data["status"] == seed_order.status
    assert "customer" in data
    assert data["customer"]["id"] == str(seed_order.customer_id)
    assert "boat" in data
    assert data["boat"]["id"] == str(seed_order.boat_id)


async def test_get_service_order_detail_from_crm_approval(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    """CRM onayından (#106) doğan servis emrinin detayında kaynak çağrı ve öneri özeti bulunur."""
    async with factory() as session:
        # Analizli ve müşteri/teknesi olan bir çağrı bul
        stmt = (
            select(Call, AnalysisRow)
            .join(AnalysisRow, Call.id == AnalysisRow.call_id)
            .where(Call.customer_id.is_not(None), Call.boat_id.is_not(None))
            .order_by(AnalysisRow.version.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        assert row is not None
        call, _ = row

        review_out = await approve_crm_record(
            session,
            call.id,
            CrmApproveIn(note="Servis emri detay testi", urgency="acil"),
        )
        await session.commit()
        assert review_out.service_order_id is not None
        order_id = review_out.service_order_id

    resp = await client.get(f"/api/v1/service-orders/{order_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == str(order_id)
    assert data["status"] == ServiceOrderStatus.YENI_ATANDI.value
    assert data["source_call"] is not None
    assert data["source_call"]["call_id"] == str(call.id)
    assert data["source_call"]["urgency"] == "acil"
    assert data["source_call"]["crm_review_status"] == "onaylandi"
    assert data["source_call"]["crm_review_note"] == "Servis emri detay testi"


async def test_update_service_order_status_workflow(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    """PATCH /api/v1/service-orders/{id}/status iş akışı durum geçişlerini doğru işletir."""
    async with factory() as session:
        order = await _create_test_order(session, status=ServiceOrderStatus.YENI_ATANDI)
        order_id = order.id

    # 1. yeni_atandi -> kesifte
    r1 = await client.patch(
        f"/api/v1/service-orders/{order_id}/status",
        json={"status": ServiceOrderStatus.KESIFTE.value},
        headers=HEADERS,
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == ServiceOrderStatus.KESIFTE.value
    assert r1.json()["completed_at"] is None

    # 2. kesifte -> onaylandi
    r2 = await client.patch(
        f"/api/v1/service-orders/{order_id}/status",
        json={"status": ServiceOrderStatus.ONAYLANDI.value},
        headers=HEADERS,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == ServiceOrderStatus.ONAYLANDI.value

    # 3. onaylandi -> devam_ediyor
    r3 = await client.patch(
        f"/api/v1/service-orders/{order_id}/status",
        json={"status": ServiceOrderStatus.DEVAM_EDIYOR.value},
        headers=HEADERS,
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == ServiceOrderStatus.DEVAM_EDIYOR.value

    # 4. devam_ediyor -> tamamlandi (completed_at dolar)
    r4 = await client.patch(
        f"/api/v1/service-orders/{order_id}/status",
        json={"status": ServiceOrderStatus.TAMAMLANDI.value},
        headers=HEADERS,
    )
    assert r4.status_code == 200
    assert r4.json()["status"] == ServiceOrderStatus.TAMAMLANDI.value
    assert r4.json()["completed_at"] is not None


async def test_update_service_order_status_invalid_transition_returns_400(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Geçersiz durum geçişinde 400 Bad Request döner."""
    async with factory() as session:
        order = await _create_test_order(session, status=ServiceOrderStatus.YENI_ATANDI)
        order_id = order.id

    # yeni_atandi -> tamamlandi (kesifte atlandı)
    r_invalid = await client.patch(
        f"/api/v1/service-orders/{order_id}/status",
        json={"status": ServiceOrderStatus.TAMAMLANDI.value},
        headers=HEADERS,
    )
    assert r_invalid.status_code == 400
    err = r_invalid.json()
    assert "error" in err
    assert "Geçersiz durum geçişi" in err["error"]["message"]


async def test_service_order_not_found_returns_404(client: AsyncClient) -> None:
    """Olmayan servis emrinde 404 döner."""
    unknown = uuid4()
    r_get = await client.get(f"/api/v1/service-orders/{unknown}", headers=HEADERS)
    assert r_get.status_code == 404

    r_patch = await client.patch(
        f"/api/v1/service-orders/{unknown}/status",
        json={"status": ServiceOrderStatus.KESIFTE.value},
        headers=HEADERS,
    )
    assert r_patch.status_code == 404


async def test_service_orders_auth_required(client: AsyncClient) -> None:
    """Servis anahtarı olmadan yapılan istekler 401 döner."""
    r = await client.get("/api/v1/service-orders")
    assert r.status_code == 401


async def test_detail_keeps_approved_analysis_after_reanalysis(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Çağrı onaydan sonra yeniden analiz edilse de emir, onaylanan sürümün alanlarını gösterir."""
    async with factory() as session:
        stmt = (
            select(Call, AnalysisRow)
            .join(AnalysisRow, Call.id == AnalysisRow.call_id)
            .where(Call.customer_id.is_not(None), Call.boat_id.is_not(None))
            .order_by(AnalysisRow.version.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        assert row is not None
        call, approved = row
        out = await approve_crm_record(session, call.id, CrmApproveIn())
        assert out.service_order_id is not None
        # Yeni analiz sürümü: farklı problem ve özet, henüz incelenmemiş.
        session.add(
            AnalysisRow(
                id=uuid4(),
                call_id=call.id,
                version=approved.version + 1,
                status="tamam",
                problem="Yeni sürümdeki farklı problem",
                summary="Yeni sürüm özeti",
            )
        )
        await session.commit()

    resp = await client.get(f"/api/v1/service-orders/{out.service_order_id}", headers=HEADERS)

    source = resp.json()["source_call"]
    assert source["problem"] == approved.problem
    assert source["summary"] == approved.summary
    assert source["crm_review_status"] == "onaylandi"

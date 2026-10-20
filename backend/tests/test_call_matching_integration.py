"""Çağrı müşteri ve tekne eşleştirme entegrasyon testleri (#119).

Yalnızca `RUN_DB_TESTS=1` iken çalışır.
Test edilen akışlar:
1. Kesin telefon eşleşmesi: Bilinen telefonla arayan çağrı doğru müşteri ve tekneye bağlanır.
2. Tek tekneli müşteride telefon eşleşmesi: Tekne adı belirtilmese bile teknesi bağlanır.
3. Ad + tekne eşleşmesi: Telefon yokken müşteri adı ve tekne adı ile eşleşme.
4. Çok tekneli müşteride belirsiz tekne: Tekne belirlenemezse yanlış tekne bağlanmaz.
5. Bilinmeyen/eşleşmeyen çağrı: `customer_id = None`, `boat_id = None`, `match_method = yok`.
6. Seed çağrılarının korunması: Mevcut seed çağrıları eşleşmelerini korur.
7. Elle eşleştirme ucu (PUT /calls/{id}/match): Başarılı eşleştirme (`match_method = elle`).
8. Elle eşleştirmede başka müşterinin teknesi seçilirse 400 hatası.
9. Olmayan çağrı veya müşteride 404 hatası.
10. Servis anahtarı doğrulama (401).
11. Otomatik eşleşen yeni çağrının CRM onayı servis emri üretebilir (#106 / #119).
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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

from app.agents.base import AnalysisContext
from app.agents.orchestrator import OrchestrationResult
from app.api.deps import get_db_session
from app.core.config import Settings
from app.db.models.ai import Call
from app.db.models.external import Boat, Customer
from app.domain.enums import (
    MatchMethod,
)
from app.main import create_app
from app.schemas.analysis import (
    AgentRun,
)
from app.schemas.api import CallCreate, CrmApproveIn
from app.services.call_ingest import create_call, run_call_analysis
from app.services.call_matching import match_call
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
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
async def client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    settings = make_settings()
    app = create_app(settings)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class DummyOrchestrator:
    """Hızlı test için sahte orkestratör."""

    def __init__(self, location: str = "Tuzla Marina") -> None:
        self.location = location

    async def run(self, ctx: AnalysisContext) -> OrchestrationResult:
        outputs = {
            "call_classifier": {
                "call_type": "servis",
                "confidence": 0.95,
                "reason": "Servis talebi",
            },
            "crm_extraction": {
                "request_category": "makine",
                "location": self.location,
                "problem": "Motor gaz yemiyor",
                "service_mode": "yerinde_servis",
                "urgency": "yuksek",
                "potential_job": "Motor arıza tespiti",
                "next_action": "servis_randevusu_olustur",
                "evidence": {"problem": "gaz yemiyor"},
            },
            "sales_analyzer": {
                "outcome": "beklemede",
                "confidence": 0.9,
            },
            "summarizer": {
                "summary": "Müşteri motor arızası bildirdi.",
                "key_points": ["Motor"],
            },
        }
        runs = [
            AgentRun(
                agent="call_classifier",
                status="ok",
                attempts=1,
                latency_ms=100,
                model="fake",
                prompt_version="1.0",
                tokens_in=10,
                tokens_out=10,
            )
        ]
        return OrchestrationResult(
            call_id=ctx.call_id,
            status="tamam",
            outputs=outputs,
            runs=runs,
        )


async def test_exact_phone_match_binds_customer_and_boat(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Telefon numarası bilinen müşteriyle eşleşirse doğru müşteri ve tekne bağlanır."""
    async with factory() as session:
        burak = (
            await session.execute(
                select(Customer).where(Customer.full_name == "Burak Çelik").limit(1)
            )
        ).scalar_one()
        ruzgar = (
            await session.execute(
                select(Boat).where(Boat.owner_id == burak.id, Boat.name == "Rüzgar").limit(1)
            )
        ).scalar_one()

        # Farklı formatta telefon numarası ile yeni çağrı
        call = Call(
            started_at=datetime.now(UTC),
            customer_phone="0533 889 12 67",  # Burak Çelik'in telefonu (+90 533 889 12 67)
            boat_name="Rüzgar",
            state="beklemede",
        )
        session.add(call)
        await session.flush()

        cust_id, boat_id, method = await match_call(session, call.id)
        assert cust_id == burak.id
        assert boat_id == ruzgar.id
        assert method == MatchMethod.TELEFON
        assert call.match_method == "telefon"
        assert call.customer_name == "Burak Çelik"


async def test_phone_match_with_single_boat_customer(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Yalnızca 1 teknesi olan müşteride tekne adı verilmese bile teknesi bağlanır."""
    async with factory() as session:
        # 1 teknesi olan müşteri bul
        stmt = (
            select(Customer, Boat)
            .join(Boat, Boat.owner_id == Customer.id)
            .group_by(Customer.id, Boat.id)
            .limit(10)
        )
        rows = (await session.execute(stmt)).all()
        # Teknesi 1 tane olanı seç
        target_cust = None
        target_boat = None
        for c, b in rows:
            boat_count = (
                (await session.execute(select(Boat).where(Boat.owner_id == c.id))).scalars().all()
            )
            if len(boat_count) == 1:
                target_cust = c
                target_boat = b
                break

        assert target_cust is not None
        assert target_boat is not None

        call = Call(
            started_at=datetime.now(UTC),
            customer_phone=target_cust.phone,
            state="beklemede",
        )
        session.add(call)
        await session.flush()

        cust_id, boat_id, method = await match_call(session, call.id)
        assert cust_id == target_cust.id
        assert boat_id == target_boat.id
        assert method == MatchMethod.TELEFON


async def test_name_and_boat_match_without_phone(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Telefon numarası yokken müşteri adı ve tekne adı ile eşleştirme yapılır."""
    async with factory() as session:
        burak = (
            await session.execute(
                select(Customer).where(Customer.full_name == "Burak Çelik").limit(1)
            )
        ).scalar_one()
        ruzgar = (
            await session.execute(
                select(Boat).where(Boat.owner_id == burak.id, Boat.name == "Rüzgar").limit(1)
            )
        ).scalar_one()

        call = Call(
            started_at=datetime.now(UTC),
            customer_name="burak celik",  # normalize edilmiş
            boat_name="ruzgar",
            state="beklemede",
        )
        session.add(call)
        await session.flush()

        cust_id, boat_id, method = await match_call(session, call.id)
        assert cust_id == burak.id
        assert boat_id == ruzgar.id
        assert method == MatchMethod.AD_TEKNE
        assert call.match_method == "ad_tekne"


async def test_ambiguous_boat_for_multi_boat_customer_leaves_boat_empty(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Çok tekneli müşteride tekne adı belirtilmemişse yanlış tekne bağlanmaz (boat_id=None)."""
    async with factory() as session:
        burak = (
            await session.execute(
                select(Customer).where(Customer.full_name == "Burak Çelik").limit(1)
            )
        ).scalar_one()
        boats = (
            (await session.execute(select(Boat).where(Boat.owner_id == burak.id))).scalars().all()
        )
        assert len(boats) >= 2

        call = Call(
            started_at=datetime.now(UTC),
            customer_phone=burak.phone,
            boat_name=None,
            state="beklemede",
        )
        session.add(call)
        await session.flush()

        cust_id, boat_id, method = await match_call(session, call.id)
        assert cust_id == burak.id
        assert boat_id is None
        assert method == MatchMethod.TELEFON
        assert call.match_method == "telefon"


async def test_unmatched_call_leaves_none_and_yok(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sistemde kayıtlı olmayan çağrı müşteri ve tekneye bağlanmaz (yok)."""
    async with factory() as session:
        call = Call(
            started_at=datetime.now(UTC),
            customer_phone="+90 599 999 99 99",
            customer_name="Bilinmeyen Kişi",
            boat_name="Bilinmeyen Tekne",
            state="beklemede",
        )
        session.add(call)
        await session.flush()

        cust_id, boat_id, method = await match_call(session, call.id)
        assert cust_id is None
        assert boat_id is None
        assert method == MatchMethod.YOK
        assert call.match_method == "yok"


async def test_seed_calls_are_preserved(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Mevcut seed çağrıları match_call çağrıldığında bozulmaz."""
    async with factory() as session:
        seed_call = (
            await session.execute(
                select(Call)
                .where(Call.customer_id.is_not(None), Call.boat_id.is_not(None))
                .limit(1)
            )
        ).scalar_one()

        orig_cust_id = seed_call.customer_id
        orig_boat_id = seed_call.boat_id

        cust_id, boat_id, _ = await match_call(session, seed_call.id)
        assert cust_id == orig_cust_id
        assert boat_id == orig_boat_id


async def test_manual_match_endpoint_success(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """PUT /api/v1/calls/{id}/match eşleşmeyen çağrıyı elle müşteriye ve tekneye bağlar."""
    async with factory() as session:
        burak = (
            await session.execute(
                select(Customer).where(Customer.full_name == "Burak Çelik").limit(1)
            )
        ).scalar_one()
        ruzgar = (
            await session.execute(
                select(Boat).where(Boat.owner_id == burak.id, Boat.name == "Rüzgar").limit(1)
            )
        ).scalar_one()

        call = Call(
            started_at=datetime.now(UTC),
            customer_name="Bilinmeyen",
            state="beklemede",
        )
        session.add(call)
        await session.commit()
        call_id = call.id

    res = await client.put(
        f"/api/v1/calls/{call_id}/match",
        headers=HEADERS,
        json={"customer_id": str(burak.id), "boat_id": str(ruzgar.id)},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["customer_id"] == str(burak.id)
    assert data["boat_id"] == str(ruzgar.id)
    assert data["match_method"] == "elle"


async def test_manual_match_invalid_boat_raises_400(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """PUT /api/v1/calls/{id}/match seçilen tekne müşteriye ait değilse 400 döner."""
    async with factory() as session:
        burak = (
            await session.execute(
                select(Customer).where(Customer.full_name == "Burak Çelik").limit(1)
            )
        ).scalar_one()
        # Başka bir müşterinin teknesini bul
        other_boat = (
            await session.execute(select(Boat).where(Boat.owner_id != burak.id).limit(1))
        ).scalar_one()

        call = Call(
            started_at=datetime.now(UTC),
            state="beklemede",
        )
        session.add(call)
        await session.commit()
        call_id = call.id

    res = await client.put(
        f"/api/v1/calls/{call_id}/match",
        headers=HEADERS,
        json={"customer_id": str(burak.id), "boat_id": str(other_boat.id)},
    )
    assert res.status_code == 400, res.text
    err = res.json()
    assert err["error"]["code"] == "invalid_boat"


async def test_manual_match_non_existent_call_or_customer_raises_404(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """PUT /api/v1/calls/{id}/match olmayan kayıt için 404 döner."""
    fake_id = uuid4()
    # Olmayan çağrı
    res = await client.put(
        f"/api/v1/calls/{fake_id}/match",
        headers=HEADERS,
        json={"customer_id": str(fake_id)},
    )
    assert res.status_code == 404

    # Var olan çağrı, olmayan müşteri
    async with factory() as session:
        call = Call(started_at=datetime.now(UTC), state="beklemede")
        session.add(call)
        await session.commit()
        call_id = call.id

    res2 = await client.put(
        f"/api/v1/calls/{call_id}/match",
        headers=HEADERS,
        json={"customer_id": str(fake_id)},
    )
    assert res2.status_code == 404


async def test_manual_match_requires_service_key_401(
    client: AsyncClient,
) -> None:
    """PUT /api/v1/calls/{id}/match yetki anahtarı olmadan 401 döner."""
    fake_id = uuid4()
    res = await client.put(
        f"/api/v1/calls/{fake_id}/match",
        json={"customer_id": str(fake_id)},
    )
    assert res.status_code == 401


async def test_automatic_matching_enables_crm_approval(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Analiz bitince otomatik eşleşen çağrı, CRM onayıyla servis emri üretebilir (#106/#119)."""
    async with factory() as session:
        burak = (
            await session.execute(
                select(Customer).where(Customer.full_name == "Burak Çelik").limit(1)
            )
        ).scalar_one()

        payload = CallCreate(
            started_at=datetime.now(UTC),
            customer_phone=burak.phone,
            boat_name="Rüzgar",
            transcript="Temsilci: Miço Usta buyrun. Müşteri: Motor arızası var.",
        )
        call_id = await create_call(session, payload)
        await session.commit()

    # Analizi çalıştır (sahte orkestratör ile)
    final_state = await run_call_analysis(
        call_id,
        factory,
        orchestrator=DummyOrchestrator(location="Tuzla Marina"),
    )
    assert final_state == "tamam"

    # Çağrının otomatik eşleştiğini doğrula
    async with factory() as session:
        call = (await session.execute(select(Call).where(Call.id == call_id))).scalar_one()
        assert call.customer_id == burak.id
        assert call.boat_id is not None
        assert call.match_method == "telefon"

        # CRM onayı artık 409 vermez, başarıyla servis emri üretir!
        review_out = await approve_crm_record(
            session,
            call_id,
            CrmApproveIn(note="Otomatik eşleşen çağrı testi"),
        )
        assert review_out.status == "onaylandi"
        assert review_out.service_order_id is not None

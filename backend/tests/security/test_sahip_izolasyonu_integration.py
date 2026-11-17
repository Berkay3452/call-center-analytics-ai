"""Sahip izolasyonu saldırıları, gerçek veritabanıyla (OWASP API1 BOLA/IDOR, LLM06).

Bir tekne sahibi başka bir sahibin oturumunu, teknesini veya kaydını kimlik tahminiyle okuyamaz,
silemez, devam ettiremez; gövdeye sahte `owner_id` koymak sahibi değiştirmez.
Yalnızca `RUN_DB_TESTS=1` iken çalışır. Veriyi kendisi kurar (iki müşteri, birer tekne ve gider),
geri alınan bir işlemde çalıştığından seed gerekmez ve veritabanında iz bırakmaz.
"""

import os
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db_session
from app.assistant import tools
from app.core.config import Settings
from app.db.models.ai import ChatMessage, ChatSession
from app.db.models.external import Boat, Customer, Expense
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, make_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

AHMET_ID = uuid4()
FATMA_ID = uuid4()
AHMET_BOAT = uuid4()
FATMA_BOAT = uuid4()


def hdr(owner: UUID) -> dict[str, str]:
    return {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(owner)}


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


@pytest.fixture(autouse=True)
async def world(factory: async_sessionmaker[AsyncSession]) -> None:
    """İki müşteri, birer tekne ve gider kaydı (işlem sonunda geri alınır)."""
    async with factory() as db:
        for owner, boat, name, amount in (
            (AHMET_ID, AHMET_BOAT, "Ahmet Deneme", "1250.00"),
            (FATMA_ID, FATMA_BOAT, "Fatma Deneme", "4300.00"),
        ):
            db.add(Customer(id=owner, full_name=name))
            await db.flush()
            db.add(Boat(id=boat, owner_id=owner, name=f"Tekne {name}"))
            await db.flush()
            db.add(
                Expense(
                    id=uuid4(),
                    boat_id=boat,
                    amount=Decimal(amount),
                    description="Akü değişimi",
                    expense_date=date(2026, 8, 15),
                )
            )
        await db.commit()


@pytest.fixture
async def client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(database_url=Settings().database_url))

    async def override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _ahmet_session(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/chat/messages", json={"question": "selam"}, headers=hdr(AHMET_ID)
    )
    assert resp.status_code == 200
    return str(resp.json()["session_id"])


async def test_other_owner_cannot_read_continue_or_delete_a_session(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> None:
    sid = await _ahmet_session(client)
    fatma = hdr(FATMA_ID)

    for url in (f"/api/v1/chat/sessions/{sid}", f"/api/v1/assistant/sessions/{sid}"):
        assert (await client.get(url, headers=fatma)).status_code == 404, url
        assert (await client.delete(url, headers=fatma)).status_code == 404, url
    cont = await client.post(
        "/api/v1/chat/messages", json={"question": "devam", "session_id": sid}, headers=fatma
    )
    assert cont.status_code == 404
    stream = await client.post(
        "/api/v1/assistant/chat", json={"question": "devam", "session_id": sid}, headers=fatma
    )
    assert stream.status_code == 404 or "event: error" in stream.text or "not_found" in stream.text

    # Yanıt, oturumun varlığını da sızdırmaz: var olmayan kimlikle aynı 404 gövdesi.
    ghost = await client.get(
        "/api/v1/chat/sessions/99999999-9999-4999-8999-999999999999", headers=fatma
    )
    real = await client.get(f"/api/v1/chat/sessions/{sid}", headers=fatma)
    assert real.status_code == ghost.status_code == 404
    assert real.json()["error"]["code"] == ghost.json()["error"]["code"]

    async with factory() as db:
        assert await db.scalar(
            select(func.count(ChatSession.id)).where(ChatSession.id == UUID(sid))
        )
        assert await db.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == UUID(sid))
        )


async def test_listing_and_bulk_delete_never_touch_another_owner(client: AsyncClient) -> None:
    sid = await _ahmet_session(client)
    fatma = hdr(FATMA_ID)

    listed = await client.get("/api/v1/chat/sessions", headers=fatma)
    assert sid not in {s["id"] for s in listed.json()}
    assert (await client.delete("/api/v1/chat/sessions", headers=fatma)).status_code == 204
    assert (
        await client.get(f"/api/v1/chat/sessions/{sid}", headers=hdr(AHMET_ID))
    ).status_code == 200


@pytest.mark.parametrize("field", ["owner_id", "ownerId", "user_id", "customer_id"])
async def test_owner_in_request_body_is_ignored_mass_assignment(
    client: AsyncClient, factory: async_sessionmaker[AsyncSession], field: str
) -> None:
    resp = await client.post(
        "/api/v1/chat/messages",
        json={"question": "selam", field: str(AHMET_ID)},
        headers=hdr(FATMA_ID),
    )

    assert resp.status_code == 200
    async with factory() as db:
        owner = await db.scalar(
            select(ChatSession.owner_id).where(ChatSession.id == UUID(resp.json()["session_id"]))
        )
    assert owner == FATMA_ID


async def test_tools_never_return_another_owners_boat_data(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as db:
        for intruder, target in ((FATMA_ID, AHMET_BOAT), (AHMET_ID, FATMA_BOAT)):
            who, boat = str(intruder), str(target)
            total = await tools.get_expense_total(who, boat_id=boat, session=db)
            assert total.total_try == Decimal("0") and total.sources == [], (who, boat)
            assert await tools.get_remaining_package(who, boat_id=boat, session=db) is None
            assert await tools.get_last_maintenance(who, boat_id=boat, session=db) is None
            stolen = await tools.get_job_expenses(who, ["akü"], boat_id=boat, session=db)
            assert stolen.items == []


async def test_tool_results_only_cite_the_callers_own_records(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as db:
        own = await tools.get_expense_total(str(AHMET_ID), session=db)
        other = await tools.get_expense_total(str(FATMA_ID), session=db)

    assert own.total_try == Decimal("1250.00") and other.total_try == Decimal("4300.00")
    assert {s.record_id for s in own.sources}.isdisjoint({s.record_id for s in other.sources})


@pytest.mark.parametrize(
    "query", ["limit=999999", "limit=-1", "limit=abc", "page=-5", "page_size=0", "page_size=100000"]
)
async def test_pagination_abuse_gives_client_error_or_bounded_page(
    client: AsyncClient, query: str
) -> None:
    resp = await client.get(f"/api/v1/calls?{query}", headers={"X-Service-Key": TEST_SERVICE_KEY})

    assert resp.status_code < 500, resp.text[:200]
    if resp.status_code == 200:
        assert len(resp.json().get("items", [])) <= 200

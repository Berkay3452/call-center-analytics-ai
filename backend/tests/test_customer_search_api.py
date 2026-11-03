"""`GET /customers` ucunun HTTP davranışı (#209): yetki, parametre doğrulama, yanıt biçimi.

Arama mantığının kendisi gerçek PostgreSQL'de `test_customer_search_integration.py` ile sınanır.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.api.deps import get_db_session
from app.api.routes import customers
from app.main import create_app
from app.schemas.api import CustomerBoatOut, CustomerSearchItem
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
CUSTOMER_ID = UUID("11111111-1111-4111-8111-111111111111")
BOAT_ID = UUID("22222222-2222-4222-8222-222222222222")


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, int]] = []

    async def search_customers(
        self, session: Any, query: str | None, limit: int = 20
    ) -> list[CustomerSearchItem]:
        self.calls.append((query, limit))
        return [
            CustomerSearchItem(
                id=CUSTOMER_ID,
                name="Burak Çelik",
                phone="0532 123 45 67",
                boats=[
                    CustomerBoatOut(id=BOAT_ID, name="Rüzgar", model="Jeanneau Sun Odyssey 440")
                ],
            )
        ]


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    spy = Spy()
    monkeypatch.setattr(customers.customer_search, "search_customers", spy.search_customers)
    return spy


@pytest.fixture
async def api(spy: Spy) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())

    async def fake_session() -> AsyncIterator[object]:
        yield object()

    app.dependency_overrides[get_db_session] = fake_session
    async for c in _client_for(app):
        yield c


async def test_search_returns_plain_array_with_boats(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.get("/api/v1/customers", params={"q": "burak"}, headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": str(CUSTOMER_ID),
            "name": "Burak Çelik",
            "phone": "0532 123 45 67",
            "boats": [{"id": str(BOAT_ID), "name": "Rüzgar", "model": "Jeanneau Sun Odyssey 440"}],
        }
    ]
    assert spy.calls == [("burak", 20)]


async def test_query_is_optional_and_limit_is_passed(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.get("/api/v1/customers", params={"limit": 5}, headers=HEADERS)

    assert resp.status_code == 200
    assert spy.calls == [(None, 5)]


@pytest.mark.parametrize("limit", [0, 51, -1, "x"])
async def test_limit_is_validated(api: httpx.AsyncClient, spy: Spy, limit: int | str) -> None:
    resp = await api.get("/api/v1/customers", params={"limit": limit}, headers=HEADERS)

    assert resp.status_code == 422
    assert spy.calls == []


async def test_overlong_query_is_rejected(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.get("/api/v1/customers", params={"q": "a" * 101}, headers=HEADERS)

    assert resp.status_code == 422
    assert spy.calls == []


async def test_requires_service_key(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.get("/api/v1/customers", params={"q": "burak"})

    assert resp.status_code == 401
    assert spy.calls == []

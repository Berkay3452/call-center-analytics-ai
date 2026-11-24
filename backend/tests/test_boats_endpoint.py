"""Tekne ucu `/boats` (#383): sahip kimliği, doğrulama, denetim. Veritabanı gerekmez."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api import deps
from app.api.routes import boats as boat_routes
from app.core.errors import ConflictError
from app.domain.audit import AuditAction
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

OWNER = uuid4()
HEADERS = {"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": str(OWNER)}


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class Spy:
    def __init__(self) -> None:
        self.added: list[dict[str, Any]] = []
        self.listed: list[UUID] = []
        self.audit: list[dict[str, Any]] = []
        self.duplicate = False
        self.session = _Session()


def _boat(**kw: Any) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "name": "Rüzgar",
        "model": None,
        "year": None,
        "marina": None,
        "created_at": datetime.now(UTC),
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    s = Spy()

    async def add(_session: object, owner_id: UUID, **kwargs: Any) -> Any:
        if s.duplicate:
            raise ConflictError("Bu adla kayıtlı bir tekneniz zaten var.")
        s.added.append({"owner_id": owner_id, **kwargs})
        return _boat(**kwargs)

    async def listing(_session: object, owner_id: UUID) -> list[Any]:
        s.listed.append(owner_id)
        return [_boat(name="Rüzgar"), _boat(name="Fırtına", year=2019)]

    async def audit(_factory: object, **kwargs: Any) -> bool:
        s.audit.append(kwargs)
        return True

    monkeypatch.setattr(boat_routes.boat_service, "add_boat", add)
    monkeypatch.setattr(boat_routes.boat_service, "list_boats", listing)
    monkeypatch.setattr(boat_routes, "record_audit_event_isolated", audit)
    return s


@pytest.fixture
async def client(spy: Spy) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(make_settings())

    async def fake_session() -> AsyncIterator[_Session]:
        yield spy.session

    app.dependency_overrides[deps.get_db_session] = fake_session
    async for c in _client_for(app):
        yield c


async def test_list_uses_signed_owner_identity(client: httpx.AsyncClient, spy: Spy) -> None:
    resp = await client.get("/api/v1/boats", headers=HEADERS)
    assert resp.status_code == 200
    assert [b["name"] for b in resp.json()] == ["Rüzgar", "Fırtına"]
    assert spy.listed == [OWNER]


async def test_add_boat_trims_input_and_takes_owner_from_identity(
    client: httpx.AsyncClient, spy: Spy
) -> None:
    other = str(uuid4())
    resp = await client.post(
        "/api/v1/boats",
        json={
            "name": "  Deniz Yıldızı ",
            "model": " Beneteau Oceanis 40 ",
            "year": 2018,
            "marina": "",
            "owner_id": other,  # yok sayılır
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    assert spy.added == [
        {
            "owner_id": OWNER,
            "name": "Deniz Yıldızı",
            "model": "Beneteau Oceanis 40",
            "year": 2018,
            "marina": None,
        }
    ]
    assert spy.session.commits == 1
    assert spy.audit[-1]["action"] is AuditAction.TEKNE_EKLENDI
    assert "Deniz" not in str(spy.audit)


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 81},
        {"name": "Tekne", "year": 1900},
        {"name": "Tekne", "year": 2999},
        {"name": "Tekne", "model": "m" * 81},
        {"name": "Te\x00kne"},
        {},
    ],
)
async def test_invalid_boat_is_422(
    client: httpx.AsyncClient, spy: Spy, body: dict[str, Any]
) -> None:
    resp = await client.post("/api/v1/boats", json=body, headers=HEADERS)
    assert resp.status_code == 422
    assert spy.added == []


async def test_duplicate_name_is_conflict(client: httpx.AsyncClient, spy: Spy) -> None:
    spy.duplicate = True
    resp = await client.post("/api/v1/boats", json={"name": "Rüzgar"}, headers=HEADERS)
    assert resp.status_code == 409
    assert spy.audit == [] and spy.session.commits == 0


async def test_boats_require_identity(client: httpx.AsyncClient, spy: Spy) -> None:
    resp = await client.get("/api/v1/boats", headers={"X-Service-Key": TEST_SERVICE_KEY})
    assert resp.status_code in (400, 401, 403)
    assert spy.listed == []

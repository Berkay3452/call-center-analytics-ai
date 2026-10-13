"""Çağrı alma uçlarının HTTP davranışı (#48). Veritabanı ve kuyruk sahtelenir.

Gerçek veritabanı üzerindeki davranış `test_call_ingest_integration.py` içindedir.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.api.deps import get_db_session
from app.api.routes import call_intake
from app.core.errors import ConflictError, NotFoundError
from app.main import create_app
from app.schemas.api import CallCreate, CallStatus
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
CALL_ID = UUID("11111111-1111-4111-8111-111111111111")
BODY = {
    "started_at": "2026-10-13T09:00:00Z",
    "customer_name": "Burak Çelik",
    "transcript": "Müşteri: Motor devir almıyor.\nTemsilci: Hangi marina?",
}


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class Spy:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.enqueued: list[UUID] = []
        self.enqueue_error: Exception | None = None
        self.states: list[tuple[str, str | None]] = []

    def enqueue(self, call_id: UUID) -> str:
        if self.enqueue_error:
            raise self.enqueue_error
        self.enqueued.append(call_id)
        return "task-1"


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    spy = Spy()

    async def create_call(session: Any, payload: CallCreate) -> UUID:
        spy.created = payload  # type: ignore[attr-defined]
        return CALL_ID

    async def request_analysis(session: Any, call_id: UUID) -> None:
        if call_id != CALL_ID:
            raise NotFoundError("Çağrı bulunamadı.")
        if getattr(spy, "busy", False):
            raise ConflictError("Çağrı şu anda işleniyor.")

    async def set_state(session: Any, call_id: UUID, state: str, error: str | None = None) -> None:
        spy.states.append((state, error))

    async def get_status(session: Any, call_id: UUID) -> CallStatus:
        if call_id != CALL_ID:
            raise NotFoundError("Çağrı bulunamadı.")
        return CallStatus(
            call_id=call_id,
            state="isleniyor",
            analysis_version=None,
            error=None,
            updated_at=datetime(2026, 10, 13, 9, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(call_intake.call_ingest, "create_call", create_call)
    monkeypatch.setattr(call_intake.call_ingest, "request_analysis", request_analysis)
    monkeypatch.setattr(call_intake.call_ingest, "set_state", set_state)
    monkeypatch.setattr(call_intake.call_ingest, "get_status", get_status)
    return spy


@pytest.fixture
async def api(spy: Spy) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())

    async def fake_session() -> AsyncIterator[FakeSession]:
        yield spy.session

    app.dependency_overrides[get_db_session] = fake_session
    app.dependency_overrides[call_intake.get_enqueue] = lambda: spy.enqueue
    async for c in _client_for(app):
        yield c


async def test_create_call_returns_202_and_enqueues(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.post("/api/v1/calls", json=BODY, headers=HEADERS)

    assert resp.status_code == 202
    assert resp.json() == {"call_id": str(CALL_ID), "state": "beklemede", "task_id": "task-1"}
    assert spy.enqueued == [CALL_ID]
    assert spy.session.commits == 1  # görev başlamadan kayıt işlenmiş olmalı


async def test_create_call_requires_text(api: httpx.AsyncClient, spy: Spy) -> None:
    body = {k: v for k, v in BODY.items() if k != "transcript"}

    resp = await api.post("/api/v1/calls", json=body, headers=HEADERS)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
    assert "transcript veya segments" in str(resp.json()["error"]["details"])
    assert spy.enqueued == []


async def test_endpoints_require_service_key(api: httpx.AsyncClient) -> None:
    for method, path in [
        ("POST", "/api/v1/calls"),
        ("POST", f"/api/v1/calls/{CALL_ID}/analyze"),
        ("GET", f"/api/v1/calls/{CALL_ID}/status"),
    ]:
        resp = await api.request(method, path, json=BODY if method == "POST" else None)
        assert resp.status_code == 401, (method, path)


async def test_enqueue_failure_marks_call_failed(api: httpx.AsyncClient, spy: Spy) -> None:
    spy.enqueue_error = ConnectionError("redis yok")

    resp = await api.post("/api/v1/calls", json=BODY, headers=HEADERS)

    assert resp.status_code == 503
    assert spy.states == [("basarisiz", "Analiz kuyruğa alınamadı.")]
    assert spy.session.commits == 2  # kayıt + başarısız durumu


async def test_reanalyze_enqueues(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.post(f"/api/v1/calls/{CALL_ID}/analyze", headers=HEADERS)

    assert resp.status_code == 202
    assert spy.enqueued == [CALL_ID]


async def test_reanalyze_unknown_call_is_404(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.post(f"/api/v1/calls/{uuid4()}/analyze", headers=HEADERS)

    assert resp.status_code == 404
    assert spy.enqueued == []


async def test_reanalyze_running_call_is_409(api: httpx.AsyncClient, spy: Spy) -> None:
    spy.busy = True  # type: ignore[attr-defined]

    resp = await api.post(f"/api/v1/calls/{CALL_ID}/analyze", headers=HEADERS)

    assert resp.status_code == 409
    assert spy.enqueued == []


async def test_status_returns_state(api: httpx.AsyncClient) -> None:
    resp = await api.get(f"/api/v1/calls/{CALL_ID}/status", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["state"] == "isleniyor"
    assert resp.json()["analysis_version"] is None


async def test_status_unknown_call_is_404(api: httpx.AsyncClient) -> None:
    resp = await api.get(f"/api/v1/calls/{uuid4()}/status", headers=HEADERS)

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_invalid_call_id_is_422(api: httpx.AsyncClient) -> None:
    resp = await api.get("/api/v1/calls/abc/status", headers=HEADERS)

    assert resp.status_code == 422

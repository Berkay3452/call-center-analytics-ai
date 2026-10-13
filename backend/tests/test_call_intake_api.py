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
        self.kinds: list[str] = []
        self.reanalysis_kind = "analysis"

    def enqueue(self, call_id: UUID, kind: str) -> str:
        if self.enqueue_error:
            raise self.enqueue_error
        self.enqueued.append(call_id)
        self.kinds.append(kind)
        return "task-1"


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    spy = Spy()

    async def create_call(session: Any, payload: CallCreate) -> UUID:
        spy.created = payload  # type: ignore[attr-defined]
        return CALL_ID

    async def request_analysis(session: Any, call_id: UUID) -> str:
        if call_id != CALL_ID:
            raise NotFoundError("Çağrı bulunamadı.")
        if getattr(spy, "busy", False):
            raise ConflictError("Çağrı şu anda işleniyor.")
        return spy.reanalysis_kind

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
    assert spy.kinds == ["analysis"]
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
    assert spy.states == [("basarisiz", "Görev kuyruğa alınamadı.")]
    assert spy.session.commits == 2  # kayıt + başarısız durumu


async def test_reanalyze_enqueues(api: httpx.AsyncClient, spy: Spy) -> None:
    resp = await api.post(f"/api/v1/calls/{CALL_ID}/analyze", headers=HEADERS)

    assert resp.status_code == 202
    assert spy.enqueued == [CALL_ID]
    assert spy.kinds == ["analysis"]


async def test_reanalyze_audio_call_without_transcript_restarts_stt(
    api: httpx.AsyncClient, spy: Spy
) -> None:
    spy.reanalysis_kind = "stt"

    resp = await api.post(f"/api/v1/calls/{CALL_ID}/analyze", headers=HEADERS)

    assert resp.status_code == 202
    assert spy.kinds == ["stt"]


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


# --- Sesli çağrı: POST /calls/audio (#49) -------------------------------------------------


@pytest.fixture
async def audio_api(
    spy: Spy, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    from app.services import audio_ingest

    async def create_audio_call(session: Any, meta: Any, stored: Any) -> UUID:
        if getattr(spy, "duplicate", False):
            raise audio_ingest.DuplicateAudioError(
                "Bu ses dosyası daha önce yüklendi.", details={"call_id": str(CALL_ID)}
            )
        spy.audio_meta = meta  # type: ignore[attr-defined]
        spy.stored = stored  # type: ignore[attr-defined]
        return CALL_ID

    monkeypatch.setattr(call_intake.audio_ingest, "create_audio_call", create_audio_call)
    app = create_app(make_settings(audio_storage_dir=str(tmp_path), audio_max_mb=1))

    async def fake_session() -> AsyncIterator[FakeSession]:
        yield spy.session

    app.dependency_overrides[get_db_session] = fake_session
    app.dependency_overrides[call_intake.get_enqueue] = lambda: spy.enqueue
    async for c in _client_for(app):
        yield c


FORM = {"started_at": "2026-10-13T09:00:00Z", "customer_name": "Burak Çelik", "marina": "Tuzla"}


async def test_audio_upload_stores_file_and_starts_stt(
    audio_api: httpx.AsyncClient, spy: Spy, tmp_path: Any
) -> None:
    resp = await audio_api.post(
        "/api/v1/calls/audio",
        data=FORM,
        files={"file": ("cagri.wav", b"RIFF-sahte-ses", "audio/wav")},
        headers=HEADERS,
    )

    assert resp.status_code == 202, resp.text
    assert spy.kinds == ["stt"]
    stored = spy.stored  # type: ignore[attr-defined]
    assert (tmp_path / stored.relative_path).read_bytes() == b"RIFF-sahte-ses"
    assert spy.audio_meta.customer_name == "Burak Çelik"  # type: ignore[attr-defined]


async def test_audio_upload_rejects_unsupported_format(audio_api: httpx.AsyncClient) -> None:
    resp = await audio_api.post(
        "/api/v1/calls/audio",
        data=FORM,
        files={"file": ("notlar.pdf", b"%PDF", "application/pdf")},
        headers=HEADERS,
    )

    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_media_type"


async def test_audio_upload_rejects_too_large_file(audio_api: httpx.AsyncClient) -> None:
    resp = await audio_api.post(
        "/api/v1/calls/audio",
        data=FORM,
        files={"file": ("uzun.mp3", b"0" * (1024 * 1024 + 1), "audio/mpeg")},
        headers=HEADERS,
    )

    assert resp.status_code == 413


async def test_audio_upload_duplicate_returns_existing_call(
    audio_api: httpx.AsyncClient, spy: Spy
) -> None:
    spy.duplicate = True  # type: ignore[attr-defined]

    resp = await audio_api.post(
        "/api/v1/calls/audio",
        data=FORM,
        files={"file": ("cagri.wav", b"RIFF", "audio/wav")},
        headers=HEADERS,
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["call_id"] == str(CALL_ID)
    assert spy.enqueued == []


async def test_audio_upload_requires_file_and_started_at(audio_api: httpx.AsyncClient) -> None:
    no_file = await audio_api.post("/api/v1/calls/audio", data=FORM, headers=HEADERS)
    no_date = await audio_api.post(
        "/api/v1/calls/audio",
        data={"customer_name": "X"},
        files={"file": ("c.wav", b"RIFF", "audio/wav")},
        headers=HEADERS,
    )

    assert no_file.status_code == 422
    assert no_date.status_code == 422

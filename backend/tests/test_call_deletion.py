"""Çağrı silme ucu ve saklama süresi (#269): HTTP davranışı, sahte oturumla (DB gerekmez)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.api.deps import get_audio_storage, get_db_session
from app.db.models.ai import Call
from app.domain.audit import AuditAction
from app.main import create_app
from app.services.call_deletion import purge_expired_calls
from app.storage.local import LocalAudioStorage
from tests.audio_fixtures import make_wav
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
CALL_ID = UUID("11111111-1111-4111-8111-111111111111")


class FakeSession:
    def __init__(self, call: Call | None) -> None:
        self.call = call
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self.commits = 0

    async def get(self, model: type[Any], ident: Any) -> Any:
        return self.call if self.call is not None and self.call.id == ident else None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def execute(self, stmt: Any) -> None:
        self.statements.append(stmt)

    async def commit(self) -> None:
        self.commits += 1


def _setup(
    tmp_path: Path, state: str = "tamam", with_audio: bool = True, missing: bool = False
) -> tuple[AsyncIterator[httpx.AsyncClient], FakeSession, LocalAudioStorage, str | None]:
    storage = LocalAudioStorage(tmp_path / "depo")
    audio_path = None
    if with_audio:
        audio_path = "ornek.wav"
        if not missing:
            (tmp_path / "depo" / audio_path).write_bytes(make_wav())
    call = Call(id=CALL_ID, started_at=datetime.now(UTC), state=state, audio_path=audio_path)
    session = FakeSession(call)
    app = create_app(make_settings())

    async def db() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_audio_storage] = lambda: storage
    return _client_for(app), session, storage, audio_path


async def test_delete_call_removes_row_audio_and_writes_audit(tmp_path: Path) -> None:
    clients, session, storage, audio_path = _setup(tmp_path)
    assert audio_path is not None
    async for client in clients:
        resp = await client.delete(f"/api/v1/calls/{CALL_ID}", headers=HEADERS)
    assert resp.status_code == 204
    assert resp.content == b""
    assert session.commits == 1
    assert len(session.statements) == 1  # DELETE FROM calls
    assert not storage.exists(audio_path)
    event = session.added[0]
    assert event.action == AuditAction.CAGRI_SILINDI.value
    assert event.target_id == str(CALL_ID)
    assert event.details == {"neden": "talep", "ses_vardi": True}


async def test_delete_call_forbidden_for_boat_owner_identity(tmp_path: Path) -> None:
    clients, session, storage, audio_path = _setup(tmp_path)
    assert audio_path is not None
    owner = {**HEADERS, "X-User-Id": "22222222-2222-4222-8222-222222222222"}
    async for client in clients:
        resp = await client.delete(f"/api/v1/calls/{CALL_ID}", headers=owner)
    assert resp.status_code == 403
    assert session.commits == 0 and not session.statements
    assert storage.exists(audio_path)  # hiçbir şey silinmedi


async def test_delete_call_requires_service_key(tmp_path: Path) -> None:
    clients, session, _, _ = _setup(tmp_path)
    async for client in clients:
        resp = await client.delete(f"/api/v1/calls/{CALL_ID}")
    assert resp.status_code == 401
    assert session.commits == 0


async def test_delete_call_unknown_is_404(tmp_path: Path) -> None:
    clients, session, _, _ = _setup(tmp_path)
    async for client in clients:
        resp = await client.delete(
            "/api/v1/calls/99999999-9999-4999-8999-999999999999", headers=HEADERS
        )
    assert resp.status_code == 404
    assert session.commits == 0


@pytest.mark.parametrize("state", ["yaziya_cevriliyor", "isleniyor"])
async def test_delete_call_in_flight_is_409_and_untouched(tmp_path: Path, state: str) -> None:
    clients, session, storage, audio_path = _setup(tmp_path, state=state)
    assert audio_path is not None
    async for client in clients:
        resp = await client.delete(f"/api/v1/calls/{CALL_ID}", headers=HEADERS)
    assert resp.status_code == 409
    assert session.commits == 0 and not session.statements
    assert storage.exists(audio_path)


async def test_delete_call_without_audio_and_with_missing_file(tmp_path: Path) -> None:
    clients, session, _, _ = _setup(tmp_path, with_audio=False)
    async for client in clients:
        resp = await client.delete(f"/api/v1/calls/{CALL_ID}", headers=HEADERS)
    assert resp.status_code == 204
    assert session.added[0].details == {"neden": "talep", "ses_vardi": False}

    clients, session, _, _ = _setup(tmp_path, missing=True)
    async for client in clients:
        resp = await client.delete(f"/api/v1/calls/{CALL_ID}", headers=HEADERS)
    assert resp.status_code == 204  # kayıt gitti; dosya zaten yoktu


async def test_retention_disabled_deletes_nothing(tmp_path: Path) -> None:
    def factory() -> Any:
        raise AssertionError("RETENTION_DAYS=0 iken veritabanına dokunulmamalı")

    result = await purge_expired_calls(
        factory, LocalAudioStorage(tmp_path), retention_days=0, batch_size=10
    )
    assert result == {"silinen": 0, "hata": 0, "atlanan_ses": 0}


def test_retention_defaults_are_safe() -> None:
    settings = make_settings()
    assert settings.retention_days == 0  # varsayılan kapalı: geliştirme verisi silinmez

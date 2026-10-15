"""Ses dosyası uç noktası birim testleri: GET /calls/{call_id}/audio (#80).

Yetki (401), olmayan çağrı (404), sesi olmayan çağrı (404), path traversal engeli (404),
başarılı akış (200, Accept-Ranges, Content-Type) ve Range isteği (206).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.api.deps import get_db_session
from app.db.models.ai import Call
from app.main import create_app
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
CALL_ID = UUID("11111111-1111-4111-8111-111111111111")
AUDIO_CONTENT = b"RIFF" + b"\x12\x34\x56\x78" * 64  # 260 byte sahte wav


class FakeSession:
    def __init__(self, call: Call | None = None) -> None:
        self.call = call

    async def get(self, model: type[Any], ident: Any) -> Any:
        if self.call is not None and self.call.id == ident:
            return self.call
        return None


@pytest.fixture
def fake_storage(tmp_path: Path) -> Path:
    storage = tmp_path / "audio_storage"
    storage.mkdir(parents=True, exist_ok=True)
    wav_file = storage / "test_audio.wav"
    wav_file.write_bytes(AUDIO_CONTENT)
    return storage


def _make_client(call: Call | None, storage_dir: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(audio_storage_dir=str(storage_dir)))
    fake_session = FakeSession(call)

    async def get_test_db() -> AsyncIterator[FakeSession]:
        yield fake_session

    app.dependency_overrides[get_db_session] = get_test_db
    return _client_for(app)


async def test_get_call_audio_requires_service_key(fake_storage: Path) -> None:
    """X-Service-Key eksik veya yanlışsa 401 Unauthorized döner."""
    call = Call(
        id=CALL_ID, started_at=datetime.now(UTC), state="tamam", audio_path="test_audio.wav"
    )
    async for client in _make_client(call, fake_storage):
        # Anahtarsız
        r1 = await client.get(f"/api/v1/calls/{CALL_ID}/audio")
        assert r1.status_code == 401
        assert r1.json()["error"]["code"] == "unauthorized"

        # Yanlış anahtar
        r2 = await client.get(
            f"/api/v1/calls/{CALL_ID}/audio", headers={"X-Service-Key": "gecersiz"}
        )
        assert r2.status_code == 401
        assert r2.json()["error"]["code"] == "unauthorized"


async def test_get_call_audio_call_not_found(fake_storage: Path) -> None:
    """Veritabanında çağrı yoksa 404 Not Found döner."""
    async for client in _make_client(None, fake_storage):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/audio", headers=HEADERS)
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "not_found"
        assert "bulunamadı" in data["error"]["message"]


async def test_get_call_audio_call_has_no_audio(fake_storage: Path) -> None:
    """Çağrı var ama audio_path boşsa 404 Not Found döner."""
    call = Call(id=CALL_ID, started_at=datetime.now(UTC), state="tamam", audio_path=None)
    async for client in _make_client(call, fake_storage):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/audio", headers=HEADERS)
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "not_found"
        assert "ses dosyası bulunamadı" in data["error"]["message"].lower()


@pytest.mark.parametrize(
    "evil_path",
    [
        "../../etc/passwd",
        "../secret.txt",
        "/etc/shadow",
        "\\Windows\\system32\\cmd.exe",
    ],
)
async def test_get_call_audio_path_traversal_rejected(fake_storage: Path, evil_path: str) -> None:
    """audio_path dışarı taşmaya çalışıyorsa 404 döner, dizin dışına çıkmaz."""
    call = Call(id=CALL_ID, started_at=datetime.now(UTC), state="tamam", audio_path=evil_path)
    async for client in _make_client(call, fake_storage):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/audio", headers=HEADERS)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


async def test_get_call_audio_missing_file_on_disk(fake_storage: Path) -> None:
    """audio_path veritabanında var ama diskte dosya yoksa 404 döner."""
    call = Call(
        id=CALL_ID, started_at=datetime.now(UTC), state="tamam", audio_path="yok_boyle_ses.wav"
    )
    async for client in _make_client(call, fake_storage):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/audio", headers=HEADERS)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


async def test_get_call_audio_success_200(fake_storage: Path) -> None:
    """Ses dosyası başarıyla 200 ve doğru başlıklarla indirilir."""
    call = Call(
        id=CALL_ID, started_at=datetime.now(UTC), state="tamam", audio_path="test_audio.wav"
    )
    async for client in _make_client(call, fake_storage):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/audio", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.headers["accept-ranges"] == "bytes"
        assert resp.content == AUDIO_CONTENT
        assert int(resp.headers["content-length"]) == len(AUDIO_CONTENT)


async def test_get_call_audio_range_request_206(fake_storage: Path) -> None:
    """Range isteğinde 206 Partial Content ve Content-Range döner."""
    call = Call(
        id=CALL_ID, started_at=datetime.now(UTC), state="tamam", audio_path="test_audio.wav"
    )
    async for client in _make_client(call, fake_storage):
        # İlk 16 bayt (0-15)
        resp = await client.get(
            f"/api/v1/calls/{CALL_ID}/audio",
            headers={**HEADERS, "Range": "bytes=0-15"},
        )
        assert resp.status_code == 206
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.headers["content-range"] == f"bytes 0-15/{len(AUDIO_CONTENT)}"
        assert int(resp.headers["content-length"]) == 16
        assert resp.content == AUDIO_CONTENT[:16]


def test_openapi_schema_includes_audio_endpoint() -> None:
    """FastAPI OpenAPI şemasında /calls/{call_id}/audio ucu yer alır."""
    app = create_app(make_settings())
    schema = app.openapi()
    paths = schema["paths"]

    endpoint = "/api/v1/calls/{call_id}/audio"
    assert endpoint in paths
    assert "get" in paths[endpoint]
    assert paths[endpoint]["get"]["operationId"] == "getCallAudio"

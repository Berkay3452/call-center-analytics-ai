"""Ses depolama soyutlaması ve sağlayıcıları sözleşme testleri (#121).

LocalAudioStorage ve FakeGcsAudioStorage gerçeklemelerinin:
- save (kaydetme, hash yolu, boyut, hata durumları)
- exists & delete (varlık kontrolü ve silme)
- open & read_bytes (içerik okuma)
- open_local_path (yerel geçici dosya bağlamı)
- get_response (HTTP 200 ve RFC 7233 Range 206 akışı)
- Path traversal saldırı koruması
- Registry ve FastAPI bağımlılık entegrasyonu
davranışlarını doğrular.
"""

import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.api.deps import get_audio_storage, get_db_session
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.models.ai import Call
from app.main import create_app
from app.services.audio_ingest import AudioTooLargeError, UnsupportedAudioError
from app.storage.base import AudioStorage, parse_range_header
from app.storage.gcs import FakeGcsAudioStorage, GcsAudioStorage
from app.storage.local import LocalAudioStorage
from app.storage.registry import build_audio_storage
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

SAMPLE_WAV = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00" + b"\x00" * 32
)
HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


# --- Sözleşme Testleri (Local ve FakeGCS için ortak) ---


@pytest.fixture(params=["local", "fake_gcs"])
def storage_backend(request: pytest.FixtureRequest, tmp_path: Path) -> AudioStorage:
    if request.param == "local":
        return LocalAudioStorage(tmp_path / "audio_storage")
    return FakeGcsAudioStorage(bucket_name="test-bucket")


def test_storage_save_and_read(storage_backend: AudioStorage) -> None:
    """Geçerli ses dosyası kaydedilir, sha256 hesaplanır ve doğru içerik okunur."""
    stream = io.BytesIO(SAMPLE_WAV)
    stored = storage_backend.save(stream, "sample.wav")

    assert stored.relative_path.endswith(".wav")
    assert stored.size_bytes == len(SAMPLE_WAV)
    assert stored.sha256 != ""
    assert storage_backend.exists(stored.relative_path) is True

    # read_bytes ve open ile içerik doğrulaması
    assert storage_backend.read_bytes(stored.relative_path) == SAMPLE_WAV
    with storage_backend.open(stored.relative_path) as f:
        assert f.read() == SAMPLE_WAV


def test_storage_save_idempotent(storage_backend: AudioStorage) -> None:
    """Aynı içerik tekrar kaydedildiğinde aynı dosya yolunu döner."""
    stored1 = storage_backend.save(io.BytesIO(SAMPLE_WAV), "call1.wav")
    stored2 = storage_backend.save(io.BytesIO(SAMPLE_WAV), "call2.wav")

    assert stored1.relative_path == stored2.relative_path
    assert stored1.sha256 == stored2.sha256


def test_storage_save_rejects_empty_file(storage_backend: AudioStorage) -> None:
    """0 baytlık dosya UnsupportedAudioError fırlatır."""
    with pytest.raises(UnsupportedAudioError):
        storage_backend.save(io.BytesIO(b""), "empty.wav", max_bytes=1000)


def test_storage_save_rejects_oversized_file(storage_backend: AudioStorage) -> None:
    """max_bytes limitini aşan dosya AudioTooLargeError fırlatır."""
    with pytest.raises(AudioTooLargeError):
        storage_backend.save(io.BytesIO(SAMPLE_WAV), "sample.wav", max_bytes=10)


def test_storage_save_rejects_unsupported_extensions(storage_backend: AudioStorage) -> None:
    """Desteklenmeyen uzantılar UnsupportedAudioError fırlatır."""
    for bad_name in ["script.exe", "doc.txt", "audio.mp3.exe", "noextension"]:
        with pytest.raises(UnsupportedAudioError):
            storage_backend.save(io.BytesIO(SAMPLE_WAV), bad_name, max_bytes=1000)


def test_storage_delete(storage_backend: AudioStorage) -> None:
    """Silinen dosya exists=False döner; olmayan dosyayı silmek False döner."""
    stored = storage_backend.save(io.BytesIO(SAMPLE_WAV), "to_delete.wav")
    assert storage_backend.exists(stored.relative_path) is True

    assert storage_backend.delete(stored.relative_path) is True
    assert storage_backend.exists(stored.relative_path) is False
    assert storage_backend.delete(stored.relative_path) is False


def test_storage_open_nonexistent_raises_not_found(storage_backend: AudioStorage) -> None:
    """Bulunmayan dosya okuma isteğinde NotFoundError fırlatılır."""
    with pytest.raises(NotFoundError):
        storage_backend.read_bytes("nonexistent/file.wav")

    with pytest.raises(NotFoundError), storage_backend.open("nonexistent/file.wav"):
        pass


def test_storage_open_local_path(storage_backend: AudioStorage) -> None:
    """open_local_path yerel bir dosya yolu döndürür ve içerik doğrulanır.

    Cloud/sahte GCS durumunda geçici dosyanın bağlam bitince silindiği test edilir.
    """
    stored = storage_backend.save(io.BytesIO(SAMPLE_WAV), "local_path_test.wav")

    yielded_path: Path | None = None
    with storage_backend.open_local_path(stored.relative_path) as path:
        yielded_path = path
        assert path.exists()
        assert path.is_file()
        assert path.read_bytes() == SAMPLE_WAV

    if isinstance(storage_backend, FakeGcsAudioStorage):
        # Geçici dosya context manager çıkışında silinmiş olmalı
        assert not yielded_path.exists()
    else:
        # LocalStorage için gerçek dosya varlığını korumalı
        assert yielded_path.exists()


def test_storage_path_traversal_protection(storage_backend: AudioStorage) -> None:
    """Dizin dışına çıkma (path traversal) girişimleri engellenir."""
    malicious_paths = [
        "../secret.wav",
        "../../etc/passwd",
        "/etc/shadow",
        "\\Windows\\System32\\cmd.exe",
        "ab/../../escaped.wav",
    ]
    for bad_path in malicious_paths:
        with pytest.raises(NotFoundError):
            storage_backend.read_bytes(bad_path)
        assert storage_backend.exists(bad_path) is False
        assert storage_backend.delete(bad_path) is False
        with pytest.raises(NotFoundError):
            storage_backend.get_response(bad_path)


# --- HTTP Response ve Range Testleri ---


def test_range_header_parsing() -> None:
    """parse_range_header RFC 7233 kurallarına göre bayt aralıklarını çözer."""
    total = 100
    assert parse_range_header("bytes=0-49", total) == (0, 49)
    assert parse_range_header("bytes=50-", total) == (50, 99)
    assert parse_range_header("bytes=-20", total) == (80, 99)
    assert parse_range_header("bytes=0-999", total) == (0, 99)  # sona kırpar
    assert parse_range_header("bytes=150-200", total) is None  # başlangıç dosya boyutundan büyük
    assert parse_range_header("invalid", total) is None
    assert parse_range_header("items=0-10", total) is None


def test_storage_get_response_full(storage_backend: AudioStorage) -> None:
    """Range başlığı yoksa 200 OK ve Accept-Ranges başlığı döner."""
    stored = storage_backend.save(io.BytesIO(SAMPLE_WAV), "response_test.wav")
    response = storage_backend.get_response(stored.relative_path)

    assert response.status_code == 200
    assert response.headers.get("accept-ranges") == "bytes"
    assert response.headers.get("content-type") == "audio/wav"
    if isinstance(storage_backend, FakeGcsAudioStorage):
        assert response.body == SAMPLE_WAV


def test_storage_get_response_partial(storage_backend: AudioStorage) -> None:
    """Range başlığı verildiğinde 206 Partial Content ve Content-Range döner."""
    stored = storage_backend.save(io.BytesIO(SAMPLE_WAV), "range_test.wav")
    total_len = len(SAMPLE_WAV)

    # 1. Başlangıç - bitiş aralığı
    response = storage_backend.get_response(stored.relative_path, range_header="bytes=0-9")
    if isinstance(storage_backend, FakeGcsAudioStorage):
        assert response.status_code == 206
        assert response.body == SAMPLE_WAV[0:10]
        assert response.headers["content-range"] == f"bytes 0-9/{total_len}"
        assert response.headers["content-length"] == "10"

    # 2. Sonek aralığı (-10 bayt)
    response_suffix = storage_backend.get_response(stored.relative_path, range_header="bytes=-10")
    if isinstance(storage_backend, FakeGcsAudioStorage):
        assert response_suffix.status_code == 206
        assert response_suffix.body == SAMPLE_WAV[-10:]
        assert response_suffix.headers["content-range"] == (
            f"bytes {total_len - 10}-{total_len - 1}/{total_len}"
        )

    # 3. Geçersiz / aralık dışı istek -> 416
    response_invalid = storage_backend.get_response(
        stored.relative_path, range_header=f"bytes={total_len + 50}-{total_len + 100}"
    )
    if isinstance(storage_backend, FakeGcsAudioStorage):
        assert response_invalid.status_code == 416
        assert response_invalid.headers["content-range"] == f"bytes */{total_len}"


# --- Registry Testleri ---


def test_build_audio_storage_local(tmp_path: Path) -> None:
    settings = make_settings(
        audio_storage_backend="local",
        audio_storage_dir=str(tmp_path / "audio"),
    )
    storage = build_audio_storage(settings)
    assert isinstance(storage, LocalAudioStorage)


def test_build_audio_storage_gcs() -> None:
    settings = make_settings(
        audio_storage_backend="gcs",
        gcs_bucket_name="my-audio-bucket",
    )
    storage = build_audio_storage(settings)
    assert isinstance(storage, GcsAudioStorage)
    assert storage.bucket_name == "my-audio-bucket"


# --- FastAPI Uç Nokta Entegrasyon Testleri (FakeGCS ile) ---


class FakeSession:
    def __init__(self, call: Call | None = None) -> None:
        self.call = call

    async def get(self, model: type[Any], ident: Any) -> Any:
        if self.call is not None and self.call.id == ident:
            return self.call
        return None


@pytest.fixture
def fake_gcs_storage() -> FakeGcsAudioStorage:
    storage = FakeGcsAudioStorage(bucket_name="api-test-bucket")
    return storage


def _make_gcs_app_client(
    call: Call | None, storage: FakeGcsAudioStorage, settings: Settings | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    app_settings = settings or make_settings(audio_storage_backend="gcs")
    app = create_app(app_settings)
    fake_session = FakeSession(call)

    async def get_test_db() -> AsyncIterator[FakeSession]:
        yield fake_session

    app.dependency_overrides[get_db_session] = get_test_db
    app.dependency_overrides[get_audio_storage] = lambda: storage
    return _client_for(app)


async def test_get_call_audio_with_fake_gcs(fake_gcs_storage: FakeGcsAudioStorage) -> None:
    """GET /calls/{id}/audio GCS depolama üzerinden 200 ve 206 akışı sağlar."""
    stored = fake_gcs_storage.save(io.BytesIO(SAMPLE_WAV), "call.wav")
    call_id = UUID("22222222-2222-4222-8222-222222222222")
    call = Call(
        id=call_id,
        started_at=datetime.now(UTC),
        state="tamam",
        audio_path=stored.relative_path,
        audio_sha256=stored.sha256,
    )

    # 1. Tam dosya isteği (200 OK)
    async for client in _make_gcs_app_client(call, fake_gcs_storage):
        resp = await client.get(f"/api/v1/calls/{call_id}/audio", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.content == SAMPLE_WAV
        assert resp.headers.get("accept-ranges") == "bytes"
        assert resp.headers.get("content-type") == "audio/wav"

        # 2. Range isteği (206 Partial Content)
        range_resp = await client.get(
            f"/api/v1/calls/{call_id}/audio",
            headers={**HEADERS, "Range": "bytes=0-15"},
        )
        assert range_resp.status_code == 206
        assert range_resp.content == SAMPLE_WAV[:16]
        assert range_resp.headers.get("content-range") == f"bytes 0-15/{len(SAMPLE_WAV)}"
        assert range_resp.headers.get("content-length") == "16"


async def test_post_call_audio_with_fake_gcs(
    fake_gcs_storage: FakeGcsAudioStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /calls/audio uç noktası FakeGCS depolama üzerinden ses dosyasını kaydeder."""
    from app.api.routes import call_intake

    saved_stored: Any = None

    class MockSession(FakeSession):
        async def commit(self) -> None:
            pass

    async def mock_create_audio_call(session: Any, meta: Any, stored: Any) -> UUID:
        nonlocal saved_stored
        saved_stored = stored
        return UUID("33333333-3333-4333-8333-333333333333")

    monkeypatch.setattr(call_intake.audio_ingest, "create_audio_call", mock_create_audio_call)

    app = create_app(make_settings(audio_storage_backend="gcs"))

    async def get_test_db() -> AsyncIterator[MockSession]:
        yield MockSession()

    app.dependency_overrides[get_db_session] = get_test_db
    app.dependency_overrides[get_audio_storage] = lambda: fake_gcs_storage
    app.dependency_overrides[call_intake.get_enqueue] = lambda: lambda cid, kind: "task-1"

    async for client in _client_for(app):
        resp = await client.post(
            "/api/v1/calls/audio",
            data={"started_at": "2026-10-22T00:00:00Z", "customer_name": "Ahmet Yılmaz"},
            files={"file": ("record.wav", SAMPLE_WAV, "audio/wav")},
            headers=HEADERS,
        )
        assert resp.status_code == 202
        assert saved_stored is not None
        assert fake_gcs_storage.exists(saved_stored.relative_path) is True
        assert fake_gcs_storage.read_bytes(saved_stored.relative_path) == SAMPLE_WAV

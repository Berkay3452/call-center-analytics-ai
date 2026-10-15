"""Sesli çağrı zinciri, gerçek PostgreSQL üzerinde (#49). Yalnızca `RUN_DB_TESTS=1` iken.

ses kaydı → STT (stub: ses yanındaki .txt) → maskeli transkript → analiz (sahte orkestratör).
Her test dış işlemde çalışır ve geri alınır.
"""

import io
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db_session
from app.core.config import Settings
from app.main import create_app
from app.schemas.api import AudioCallMeta
from app.services.audio_ingest import (
    DuplicateAudioError,
    create_audio_call,
    run_transcription,
    store_audio,
)
from app.services.call_ingest import get_status, request_analysis, run_call_analysis
from app.stt.providers import StubTranscriber
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings
from tests.test_call_ingest_integration import FakeRunner

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

SIDECAR = (
    "Temsilci: Miço Usta, buyurun.\n"
    "Müşteri: Ben Burak Çelik, numaram 0532 123 45 67. Tuzla Marina'da motor tekliyor."
)


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


def delete_files(folder: Path) -> None:
    for f in folder.iterdir():
        f.unlink()


async def upload(
    factory: async_sessionmaker[AsyncSession], storage: Path, content: bytes, sidecar: str | None
) -> UUID:
    stored = store_audio(io.BytesIO(content), "cagri.wav", storage, max_bytes=1_000_000)
    if sidecar is not None:
        (storage / stored.relative_path).with_suffix(".txt").write_text(sidecar, encoding="utf-8")
    meta = AudioCallMeta(
        started_at=datetime(2026, 10, 13, 9, 0, tzinfo=UTC), customer_name="Burak Çelik"
    )
    async with factory() as session, session.begin():
        return await create_audio_call(session, meta, stored)


async def test_audio_call_goes_through_stt_and_analysis(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    call_id = await upload(factory, tmp_path, b"RIFF-ses-1", SIDECAR)

    stt_state = await run_transcription(call_id, factory, StubTranscriber(), storage_dir=tmp_path)
    assert stt_state == "beklemede"  # analiz kuyruğa alınmaya hazır

    row = (
        await conn.execute(
            text(
                "SELECT c.duration_s, t.full_text, t.masked_text FROM calls c"
                " JOIN transcripts t ON t.call_id = c.id WHERE c.id = :c"
            ),
            {"c": call_id},
        )
    ).one()
    assert row.duration_s is not None  # süre STT'den dolduruldu
    assert "0532 123 45 67" in row.full_text
    assert "0532" not in row.masked_text
    assert "Burak" not in row.masked_text

    final = await run_call_analysis(call_id, factory, orchestrator=FakeRunner())
    assert final == "tamam"
    async with factory() as session:
        status = await get_status(session, call_id)
    assert (status.state, status.analysis_version) == ("tamam", 1)


async def test_stt_failure_marks_call_failed_and_can_be_retried(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    call_id = await upload(factory, tmp_path, b"RIFF-ses-2", sidecar=None)  # stub metni yok

    state = await run_transcription(call_id, factory, StubTranscriber(), storage_dir=tmp_path)

    assert state == "basarisiz"
    async with factory() as session:
        status = await get_status(session, call_id)
    assert status.state == "basarisiz"
    assert status.error is not None
    assert "Yazıya çevirme başarısız" in status.error

    # Transkripti olmayan sesli çağrı yeniden işlenince önce STT çalışır.
    async with factory() as session, session.begin():
        assert await request_analysis(session, call_id) == "stt"


async def test_same_audio_cannot_be_uploaded_twice(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    first = await upload(factory, tmp_path, b"RIFF-ayni", SIDECAR)

    with pytest.raises(DuplicateAudioError) as info:
        await upload(factory, tmp_path, b"RIFF-ayni", SIDECAR)

    assert info.value.details == {"call_id": str(first)}


async def test_missing_audio_file_fails_cleanly(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    call_id = await upload(factory, tmp_path, b"RIFF-ses-3", SIDECAR)
    delete_files(tmp_path)  # dosya diskten silinmiş

    state = await run_transcription(call_id, factory, StubTranscriber(), storage_dir=tmp_path)

    assert state == "basarisiz"


async def test_get_call_audio_endpoint_integration(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Gerçek veritabanında ses dosyası 200 ve Range 206 ile döner (#80)."""
    audio_data = b"RIFF" + b"\x00" * 100
    call_id = await upload(factory, tmp_path, audio_data, SIDECAR)

    settings = make_settings(audio_storage_dir=str(tmp_path))
    app = create_app(settings)

    async def get_test_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = get_test_session

    async for client in _client_for(app):
        # 1. 200 OK
        resp = await client.get(
            f"/api/v1/calls/{call_id}/audio", headers={"X-Service-Key": TEST_SERVICE_KEY}
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.headers["accept-ranges"] == "bytes"
        assert resp.content == audio_data

        # 2. 206 Partial Content (Range: bytes=0-9)
        resp_range = await client.get(
            f"/api/v1/calls/{call_id}/audio",
            headers={"X-Service-Key": TEST_SERVICE_KEY, "Range": "bytes=0-9"},
        )
        assert resp_range.status_code == 206
        assert resp_range.headers["content-range"] == f"bytes 0-9/{len(audio_data)}"
        assert resp_range.content == audio_data[:10]

"""Takılı kalan çağrıları kurtarma ve eski görev yönetimi testleri (#107).

- Eski / silinmiş çağrıya ait Celery görevleri (orphan tasks) sessizce uyarı loglar
  ve çökmek yerine 'bulunamadi' döner.
- STUCK_CALL_TIMEOUT_MIN süresini aşan ve 'beklemede', 'yaziya_cevriliyor' veya 'isleniyor'
  durumunda kalan çağrılar ilk tespitte kurtarılır; ikinci tespitte 'basarisiz' yapılır.
- Yakın zamanda güncellenmiş (taze) çağrılara dokunulmaz.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.db.models.ai import Call, Transcript
from app.services.call_ingest import request_analysis
from app.services.call_recovery import (
    FINAL_TIMEOUT_ERROR,
    RETRY_MARKER_PREFIX,
    recover_stuck_calls,
)
from app.workers.tasks.analysis import analyze_call
from app.workers.tasks.stt import transcribe_audio
from app.workers.tasks.system import recover_stuck_calls_task

# --- Birim Testler (Veritabanı gerektirmez) ----------------------------------------------------


def test_analyze_call_orphan_task_returns_bulunamadi_without_raising() -> None:
    """Veritabanında bulunmayan bir çağrı için analiz görevi hata fırlatmaz, 'bulunamadi' döner."""
    from app.core.errors import NotFoundError

    with (
        patch(
            "app.workers.tasks.analysis.run_async", side_effect=NotFoundError("Çağrı bulunamadı.")
        ),
        patch("app.workers.tasks.analysis._analyze"),
    ):
        result = analyze_call(str(uuid4()))
        assert result == "bulunamadi"


def test_analyze_call_invalid_uuid_returns_bulunamadi() -> None:
    """Geçersiz UUID ile çağrılan analiz görevi 'bulunamadi' döner."""
    assert analyze_call("gecersiz-uuid") == "bulunamadi"


def test_transcribe_audio_orphan_task_returns_bulunamadi_without_raising() -> None:
    """Veritabanında bulunmayan bir çağrı için STT görevi hata fırlatmaz, 'bulunamadi' döner."""
    from app.core.errors import NotFoundError

    with (
        patch("app.workers.tasks.stt.run_async", side_effect=NotFoundError("Çağrı bulunamadı.")),
        patch("app.workers.tasks.stt._transcribe"),
    ):
        result = transcribe_audio(str(uuid4()))
        assert result == "bulunamadi"


def test_transcribe_audio_invalid_uuid_returns_bulunamadi() -> None:
    """Geçersiz UUID ile çağrılan STT görevi 'bulunamadi' döner."""
    assert transcribe_audio("gecersiz-uuid") == "bulunamadi"


# --- Entegrasyon Testleri (Gerçek PostgreSQL, RUN_DB_TESTS=1) -----------------------------------

db_test = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
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
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


async def _create_test_call(
    session: AsyncSession,
    state: str,
    *,
    minutes_ago: int = 15,
    error: str | None = None,
    audio_path: str | None = None,
    with_transcript: bool = False,
) -> UUID:
    call_id = uuid4()
    old_time = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    session.add(
        Call(
            id=call_id,
            started_at=old_time,
            state=state,
            error=error,
            audio_path=audio_path,
            created_at=old_time,
            updated_at=old_time,
        )
    )
    if with_transcript:
        session.add(
            Transcript(
                id=uuid4(),
                call_id=call_id,
                full_text="Test transkripti",
                masked_text="Test transkripti",
                created_at=old_time,
            )
        )
    await session.flush()
    # updated_at'in gerçekten eski kalması için doğrudan SQL ile güncelliyoruz.
    await session.execute(
        text("UPDATE calls SET updated_at = :old_time WHERE id = :id"),
        {"old_time": old_time, "id": call_id},
    )
    await session.commit()
    return call_id


@db_test
async def test_stuck_call_first_timeout_is_requeued(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """10 dakikadan eski 'isleniyor' çağrısı ilk tespitte 'beklemede' yapılır."""
    async with factory() as session:
        call_id = await _create_test_call(
            session,
            state="isleniyor",
            minutes_ago=15,
            with_transcript=True,
        )

    with patch("app.services.call_recovery._enqueue_recovery_task") as mock_enqueue:
        counts = await recover_stuck_calls(factory, timeout_min=10, enqueue=True)
        assert counts["retried"] == 1
        assert counts["failed"] == 0
        mock_enqueue.assert_called_once_with(call_id, needs_stt=False)

    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call is not None
        assert call.state == "beklemede"
        assert call.error is not None
        assert RETRY_MARKER_PREFIX in call.error


@db_test
async def test_stuck_call_second_timeout_marked_as_failed(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """İkinci kez takılan çağrı 'basarisiz' yapılır ve 'yeniden deneyin' mesajı yazılır."""
    async with factory() as session:
        call_id = await _create_test_call(
            session,
            state="isleniyor",
            minutes_ago=15,
            error=f"{RETRY_MARKER_PREFIX} (deneme 1)",
            with_transcript=True,
        )

    with patch("app.services.call_recovery._enqueue_recovery_task") as mock_enqueue:
        counts = await recover_stuck_calls(factory, timeout_min=10, enqueue=True)
        assert counts["retried"] == 0
        assert counts["failed"] == 1
        mock_enqueue.assert_not_called()

    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call is not None
        assert call.state == "basarisiz"
        assert call.error == FINAL_TIMEOUT_ERROR


@db_test
async def test_fresh_call_is_untouched(factory: async_sessionmaker[AsyncSession]) -> None:
    """Yakın zamanda güncellenmiş (taze) çağrı kurtarma taramasından etkilenmez."""
    async with factory() as session:
        call_id = await _create_test_call(
            session,
            state="isleniyor",
            minutes_ago=2,
            with_transcript=True,
        )

    counts = await recover_stuck_calls(factory, timeout_min=10, enqueue=False)
    assert counts["retried"] == 0
    assert counts["failed"] == 0

    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call is not None
        assert call.state == "isleniyor"
        assert call.error is None


@db_test
async def test_stuck_audio_call_without_transcript_requeues_stt(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Transkripti olmayan ama sesi olan takılı çağrı STT görevine yönlendirilir."""
    async with factory() as session:
        call_id = await _create_test_call(
            session,
            state="yaziya_cevriliyor",
            minutes_ago=20,
            audio_path="seed/call_001.wav",
            with_transcript=False,
        )

    with patch("app.services.call_recovery._enqueue_recovery_task") as mock_enqueue:
        counts = await recover_stuck_calls(factory, timeout_min=10, enqueue=True)
        assert counts["retried"] == 1
        mock_enqueue.assert_called_once_with(call_id, needs_stt=True)


@db_test
async def test_manual_reanalysis_clears_error_after_failure(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Zaman aşımından başarısız olan çağrı yeniden analiz edilince hata temizlenir."""
    async with factory() as session:
        call_id = await _create_test_call(
            session,
            state="basarisiz",
            minutes_ago=30,
            error=FINAL_TIMEOUT_ERROR,
            with_transcript=True,
        )
        task_kind = await request_analysis(session, call_id)
        await session.commit()
        assert task_kind == "analysis"

    async with factory() as session:
        call = await session.get(Call, call_id)
        assert call is not None
        assert call.state == "beklemede"
        assert call.error is None


def test_celery_task_recover_stuck_calls_runs_cleanly() -> None:
    """Celery'nin recover_stuck_calls_task görevi başarıyla çalışır ve özet döner."""
    with patch("app.workers.tasks.system.get_settings") as mock_settings:
        mock_settings.return_value = Settings(stuck_call_timeout_min=10)
        with patch("app.workers.tasks.system.recover_stuck_calls") as mock_recover:

            async def fake_recover(*args: Any, **kwargs: Any) -> dict[str, int]:
                return {"retried": 0, "failed": 0, "total": 0}

            mock_recover.side_effect = fake_recover
            res = recover_stuck_calls_task()
            assert isinstance(res, dict)
            assert "retried" in res
            assert "failed" in res

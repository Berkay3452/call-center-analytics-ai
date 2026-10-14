"""Analiz kaydı ve okuma, gerçek PostgreSQL üzerinde (#47). Yalnızca `RUN_DB_TESTS=1` iken.

Her test dış bir işlemde çalışır ve sonunda geri alınır; `commit` yapan kod (kayıtçı) savepoint
kullanır, veritabanında iz kalmaz.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.base import Segment
from app.agents.orchestrator import OrchestrationResult
from app.core.config import Settings
from app.schemas.analysis import AgentRun, AnalysisResult
from app.services.analysis_store import (
    CallNotFoundError,
    DbRunRecorder,
    get_latest_analysis,
    save_analysis,
    save_transcript,
)
from tests.test_analysis_store import full_result

pytestmark = pytest.mark.skipif(
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
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


async def new_call(conn: AsyncConnection) -> UUID:
    result = await conn.execute(
        text("INSERT INTO calls (started_at) VALUES (:t) RETURNING id"),
        {"t": datetime(2026, 10, 13, 9, 0, tzinfo=UTC)},
    )
    value: UUID = result.scalar_one()
    return value


def result_for(call_id: UUID) -> AnalysisResult:
    return full_result().model_copy(update={"call_id": call_id})


async def test_save_analysis_writes_versions_and_agent_runs(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    call_id = await new_call(conn)
    async with factory() as session:
        v1 = await save_analysis(session, result_for(call_id))
        v2 = await save_analysis(session, result_for(call_id))
        latest = await get_latest_analysis(session, call_id)
        await session.commit()  # dış işleme yaz (savepoint); conn ile doğrulanacak

    assert (v1, v2) == (1, 2)
    assert latest is not None
    assert latest.version == 2
    assert latest.status == "tamam"
    assert latest.crm is not None
    assert latest.crm.location == "Tuzla Marina"
    assert latest.summary is not None
    assert len(latest.runs) == 4
    assert latest.runs[0].model == "m"
    count = await conn.scalar(
        text("SELECT count(*) FROM analysis_results WHERE call_id = :c"), {"c": call_id}
    )
    assert count == 2  # eski sürüm silinmedi


async def test_get_latest_analysis_without_analysis_is_none(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    call_id = await new_call(conn)
    async with factory() as session:
        assert await get_latest_analysis(session, call_id) is None


async def test_unknown_call_is_rejected(factory: async_sessionmaker[AsyncSession]) -> None:
    missing = UUID("00000000-0000-4000-8000-000000000001")
    async with factory() as session:
        with pytest.raises(CallNotFoundError):
            await save_analysis(session, result_for(missing))
        with pytest.raises(CallNotFoundError):
            await save_transcript(session, missing, [])


async def test_save_transcript_replaces_previous_segments(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    call_id = await new_call(conn)
    first = [
        Segment(idx=0, speaker="rep", start_ms=0, end_ms=2000, text_masked="Buyurun."),
        Segment(
            idx=1, speaker="customer", start_ms=2000, end_ms=5000, text_masked="Motor tekliyor."
        ),
        Segment(idx=2, speaker="unknown", start_ms=5000, end_ms=6000, text_masked="Evet."),
    ]
    raw = ["Buyurun.", "Motor tekliyor.", "Evet."]
    async with factory() as session:
        t1 = await save_transcript(session, call_id, first, raw_texts=raw)
        t2 = await save_transcript(session, call_id, first[:2])
        await session.commit()

    assert t1 == t2  # aynı çağrının tek transkripti güncellenir
    rows = (
        await conn.execute(
            text(
                "SELECT segment_index, speaker FROM transcript_segments"
                " WHERE transcript_id = :t ORDER BY segment_index"
            ),
            {"t": t2},
        )
    ).all()
    assert [tuple(r) for r in rows] == [(0, "rep"), (1, "customer")]
    full = await conn.scalar(text("SELECT full_text FROM transcripts WHERE id = :t"), {"t": t2})
    assert full == "Buyurun.\nMotor tekliyor."


async def test_unknown_speaker_is_stored_as_customer(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    call_id = await new_call(conn)
    seg = Segment(idx=0, speaker="unknown", start_ms=0, end_ms=1000, text_masked="Alo.")
    async with factory() as session:
        t = await save_transcript(session, call_id, [seg])
        await session.commit()
    speaker = await conn.scalar(
        text("SELECT speaker FROM transcript_segments WHERE transcript_id = :t"), {"t": t}
    )
    assert speaker == "customer"


async def test_db_run_recorder_persists_orchestration_result(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    call_id = await new_call(conn)
    full = result_for(call_id)
    assert full.classification is not None
    assert full.crm is not None
    outcome = OrchestrationResult(
        call_id=call_id,
        status="tamam",
        outputs={
            "call_classifier": full.classification.model_dump(mode="json"),
            "crm_extraction": full.crm.model_dump(mode="json"),
        },
        runs=[AgentRun(agent="call_classifier", status="ok", attempts=1, latency_ms=900)],
    )

    await DbRunRecorder(factory).record(outcome)

    async with factory() as session:
        latest = await get_latest_analysis(session, call_id)
    assert latest is not None
    assert latest.classification is not None
    assert latest.classification.call_type == "servis"
    assert [r.agent for r in latest.runs] == ["call_classifier"]

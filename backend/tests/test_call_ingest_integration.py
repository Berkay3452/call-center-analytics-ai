"""Çağrı alma ve analiz akışı, gerçek PostgreSQL üzerinde (#48). Yalnızca `RUN_DB_TESTS=1` iken.

Orkestratör sahtedir (LLM çağrılmaz); veritabanı, durum geçişleri ve maskeleme gerçektir.
Her test dış işlemde çalışır ve geri alınır.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.base import AnalysisContext
from app.agents.orchestrator import OrchestrationResult
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.schemas.api import CallCreate
from app.services.analysis_store import get_latest_analysis
from app.services.call_ingest import (
    NoTranscriptError,
    create_call,
    get_status,
    request_analysis,
    run_call_analysis,
    set_state,
)
from tests.test_analysis_store import full_result

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

TRANSCRIPT = (
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


class FakeRunner:
    """Orkestratör yerine geçer: aldığı bağlamı kaydeder, hazır sonuç döner veya hata verir."""

    def __init__(self, status: str = "tamam", crash: Exception | None = None) -> None:
        self.status = status
        self.crash = crash
        self.seen: list[AnalysisContext] = []

    async def run(self, ctx: AnalysisContext) -> OrchestrationResult:
        self.seen.append(ctx)
        if self.crash:
            raise self.crash
        full = full_result()
        assert full.classification is not None
        assert full.crm is not None
        if self.status == "basarisiz":
            return OrchestrationResult(
                call_id=ctx.call_id, status="basarisiz", errors={"call_classifier": "LLM yok"}
            )
        return OrchestrationResult(
            call_id=ctx.call_id,
            status="tamam",
            outputs={
                "call_classifier": full.classification.model_dump(mode="json"),
                "crm_extraction": full.crm.model_dump(mode="json"),
            },
        )


async def new_call(factory: async_sessionmaker[AsyncSession]) -> UUID:
    payload = CallCreate(
        started_at=datetime(2026, 10, 13, 9, 0, tzinfo=UTC),
        customer_name="Burak Çelik",
        transcript=TRANSCRIPT,
    )
    async with factory() as session, session.begin():
        return await create_call(session, payload)


async def state_of(factory: async_sessionmaker[AsyncSession], call_id: UUID) -> str:
    async with factory() as session:
        return (await get_status(session, call_id)).state


async def test_create_call_stores_masked_and_raw_transcript(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    call_id = await new_call(factory)

    assert await state_of(factory, call_id) == "beklemede"
    rows = (
        await conn.execute(
            text(
                "SELECT s.speaker, s.text, s.masked_text FROM transcript_segments s"
                " JOIN transcripts t ON t.id = s.transcript_id WHERE t.call_id = :c"
                " ORDER BY s.segment_index"
            ),
            {"c": call_id},
        )
    ).all()
    assert [r.speaker for r in rows] == ["rep", "customer"]
    assert "0532 123 45 67" in rows[1].text  # ham metin saklanır
    assert "0532" not in rows[1].masked_text  # LLM'e giden metin maskeli
    assert "[TELEFON]" in rows[1].masked_text
    assert "[İSİM]" in rows[1].masked_text
    assert "Burak" not in rows[1].masked_text


async def test_run_analysis_success_saves_result_and_state(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    call_id = await new_call(factory)
    runner = FakeRunner()

    final = await run_call_analysis(call_id, factory, orchestrator=runner)

    assert final == "tamam"
    # Agent'lar yalnızca maskeli metni görür.
    seen = " ".join(s.text_masked for s in runner.seen[0].segments)
    assert "0532" not in seen
    assert "Burak" not in seen
    async with factory() as session:
        status = await get_status(session, call_id)
        analysis = await get_latest_analysis(session, call_id)
    assert (status.state, status.analysis_version, status.error) == ("tamam", 1, None)
    assert analysis is not None
    assert analysis.classification is not None


async def test_run_analysis_total_failure_sets_error(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    call_id = await new_call(factory)

    final = await run_call_analysis(call_id, factory, orchestrator=FakeRunner("basarisiz"))

    assert final == "basarisiz"
    async with factory() as session:
        status = await get_status(session, call_id)
    assert status.state == "basarisiz"
    assert status.error is not None
    assert "call_classifier" in status.error


async def test_run_analysis_crash_does_not_leave_call_stuck(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    call_id = await new_call(factory)

    final = await run_call_analysis(
        call_id, factory, orchestrator=FakeRunner(crash=RuntimeError("beklenmedik"))
    )

    assert final == "basarisiz"
    async with factory() as session:
        status = await get_status(session, call_id)
    assert status.state == "basarisiz"
    assert status.error is not None
    assert "beklenmedik" in status.error


async def test_request_analysis_rules(factory: async_sessionmaker[AsyncSession]) -> None:
    call_id = await new_call(factory)
    await run_call_analysis(call_id, factory, orchestrator=FakeRunner())

    # Biten çağrı yeniden analize alınabilir; yeni sürüm eklenir.
    async with factory() as session, session.begin():
        await request_analysis(session, call_id)
    assert await state_of(factory, call_id) == "beklemede"
    await run_call_analysis(call_id, factory, orchestrator=FakeRunner())
    async with factory() as session:
        assert (await get_status(session, call_id)).analysis_version == 2

    # İşlenmekte olan çağrı tekrar başlatılamaz.
    async with factory() as session, session.begin():
        await set_state(session, call_id, "isleniyor")
    async with factory() as session, session.begin():
        with pytest.raises(ConflictError):
            await request_analysis(session, call_id)


async def test_request_analysis_unknown_call_and_missing_transcript(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession]
) -> None:
    async with factory() as session, session.begin():
        with pytest.raises(NotFoundError):
            await request_analysis(session, uuid4())
        with pytest.raises(NotFoundError):
            await get_status(session, uuid4())

    result = await conn.execute(text("INSERT INTO calls (started_at) VALUES (now()) RETURNING id"))
    bare_call: UUID = result.scalar_one()  # transkripti olmayan çağrı
    async with factory() as session, session.begin():
        with pytest.raises(NoTranscriptError):
            await request_analysis(session, bare_call)


async def test_call_without_text_is_rejected(factory: async_sessionmaker[AsyncSession]) -> None:
    payload = CallCreate(
        started_at=datetime(2026, 10, 13, 9, 0, tzinfo=UTC), transcript="\n  \nMüşteri:  \n"
    )
    async with factory() as session, session.begin():
        with pytest.raises(NoTranscriptError):
            await create_call(session, payload)


async def test_matching_failure_does_not_lose_the_analysis(
    factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eşleştirme (#119) yardımcı bir adımdır: hata verirse analiz yine kaydedilir."""
    from app.services import call_ingest

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("eşleştirme patladı")

    monkeypatch.setattr(call_ingest, "match_call", boom)
    call_id = await new_call(factory)

    final = await run_call_analysis(call_id, factory, orchestrator=FakeRunner())

    assert final == "tamam"
    assert await state_of(factory, call_id) == "tamam"

"""Çağrı silme: gerçek veritabanında kalıntı yok (#269). Yalnızca `RUN_DB_TESTS=1` iken çalışır.

Her test geri alınan bir işlemde ve geçici bir ses klasöründe çalışır: ortak geliştirme verisine
dokunulmaz (silme yalnızca bu testin kendi yarattığı çağrıya uygulanır).
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.orchestrator import OrchestrationResult
from app.core.config import Settings
from app.db.models.ai import AnalysisResult, Call, CrmReview
from app.db.models.audit import AuditLog
from app.db.models.external import Boat, Customer, ServiceOrder
from app.domain.audit import AuditAction
from app.schemas.analysis import AgentRun
from app.schemas.api import CallCreate
from app.services.analysis_store import DbRunRecorder
from app.services.call_deletion import delete_call, purge_expired_calls
from app.services.call_ingest import create_call
from app.storage.local import LocalAudioStorage
from tests.audio_fixtures import make_wav
from tests.test_analysis_store import full_result

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

PHONE = "0532 123 45 67"  # sentetik test numarası
TRANSCRIPT = (
    f"Temsilci: Miço Usta, buyurun.\nMüşteri: Ben Burak Çelik, numaram {PHONE}. Motor tekliyor."
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


async def _count(conn: AsyncConnection, sql: str, **params: object) -> int:
    return int(await conn.scalar(text(sql), params) or 0)


async def _seed_call(
    factory: async_sessionmaker[AsyncSession],
    storage: LocalAudioStorage,
    tmp_dir: Path,
    *,
    started_at: datetime,
    suffix: str,
) -> tuple[UUID, str]:
    """Transkript, analiz, CRM önerisi, servis emri ve ses dosyası olan bir çağrı kurar."""
    async with factory() as session:
        call_id = await create_call(
            session,
            CallCreate(started_at=started_at, customer_name="Burak Çelik", transcript=TRANSCRIPT),
        )
        audio_name = f"silme-testi-{suffix}.wav"
        (tmp_dir / audio_name).write_bytes(make_wav())
        call = await session.get(Call, call_id)
        assert call is not None
        call.audio_path = audio_name
        call.audio_sha256 = (suffix * 64)[:64]
        await session.commit()

    full = full_result()
    assert full.classification is not None and full.crm is not None
    await DbRunRecorder(factory).record(
        OrchestrationResult(
            call_id=call_id,
            status="tamam",
            outputs={
                "call_classifier": full.classification.model_dump(mode="json"),
                "crm_extraction": full.crm.model_dump(mode="json"),
            },
            runs=[AgentRun(agent="call_classifier", status="ok", attempts=1, latency_ms=10)],
        )
    )
    async with factory() as session:
        customer = Customer(full_name="Silme Testi Müşterisi")
        session.add(customer)
        await session.flush()
        boat = Boat(owner_id=customer.id, name="Silme Testi Teknesi")
        session.add(boat)
        await session.flush()
        order = ServiceOrder(boat_id=boat.id, customer_id=customer.id, source_call_id=call_id)
        analysis_id = await session.scalar(
            select(AnalysisResult.id).where(AnalysisResult.call_id == call_id)
        )
        assert analysis_id is not None
        session.add(order)
        session.add(CrmReview(analysis_id=analysis_id, call_id=call_id))
        await session.commit()
        return call_id, str(order.id)


async def test_delete_call_leaves_no_residue(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalAudioStorage(tmp_path)
    call_id, order_id = await _seed_call(
        factory, storage, tmp_path, started_at=datetime(2026, 11, 1, tzinfo=UTC), suffix="a"
    )
    other_id, _ = await _seed_call(
        factory, storage, tmp_path, started_at=datetime(2026, 11, 2, tzinfo=UTC), suffix="b"
    )
    phone_rows_before = await _count(
        conn, "SELECT count(*) FROM transcript_segments WHERE text LIKE :p", p=f"%{PHONE}%"
    )
    assert phone_rows_before >= 2  # iki çağrının müşteri turları

    async with factory() as session:
        result = await delete_call(session, storage, call_id)

    assert result.had_audio and result.audio_deleted
    args = {"c": call_id}
    assert await _count(conn, "SELECT count(*) FROM calls WHERE id = :c", **args) == 0
    assert await _count(conn, "SELECT count(*) FROM transcripts WHERE call_id = :c", **args) == 0
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM transcript_segments s JOIN transcripts t"
            " ON t.id = s.transcript_id WHERE t.call_id = :c",
            **args,
        )
        == 0
    )
    assert (
        await _count(conn, "SELECT count(*) FROM analysis_results WHERE call_id = :c", **args) == 0
    )
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM agent_runs r JOIN analysis_results a ON a.id = r.analysis_id"
            " WHERE a.call_id = :c",
            **args,
        )
        == 0
    )
    assert await _count(conn, "SELECT count(*) FROM crm_reviews WHERE call_id = :c", **args) == 0
    # Silinen çağrının ham müşteri turu (telefon içeren) hiçbir tabloda kalmadı: yalnızca bir satır
    # (diğer çağrının turu) azaldı.
    assert (
        await _count(
            conn, "SELECT count(*) FROM transcript_segments WHERE text LIKE :p", p=f"%{PHONE}%"
        )
        == phone_rows_before - 1
    )
    assert not (tmp_path / "silme-testi-a.wav").exists()
    # Servis emri iş kaydıdır: kalır, çağrıyla bağı kopar.
    source = await conn.scalar(
        text("SELECT source_call_id FROM service_orders WHERE id = :o"), {"o": order_id}
    )
    assert source is None
    # Diğer çağrı etkilenmedi.
    assert await _count(conn, "SELECT count(*) FROM calls WHERE id = :c", c=other_id) == 1
    assert (tmp_path / "silme-testi-b.wav").exists()


async def test_delete_writes_audit_event_without_personal_data(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalAudioStorage(tmp_path)
    call_id, _ = await _seed_call(
        factory, storage, tmp_path, started_at=datetime(2026, 11, 1, tzinfo=UTC), suffix="c"
    )
    async with factory() as session:
        await delete_call(session, storage, call_id, reason="talep")

    async with factory() as session:
        events = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.CAGRI_SILINDI.value,
                    AuditLog.target_id == str(call_id),
                )
            )
        )
    assert len(events) == 1
    blob = f"{events[0].details} {events[0].target_id} {events[0].actor_role}"
    assert events[0].details == {"neden": "talep", "ses_vardi": True}
    for forbidden in (PHONE, "0532", "Burak", "Çelik"):
        assert forbidden not in blob


async def test_retention_purges_only_expired_and_finished_calls(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalAudioStorage(tmp_path)
    old_id, _ = await _seed_call(
        factory, storage, tmp_path, started_at=datetime(2000, 1, 1, tzinfo=UTC), suffix="d"
    )
    new_id, _ = await _seed_call(
        factory, storage, tmp_path, started_at=datetime(2001, 3, 1, tzinfo=UTC), suffix="e"
    )
    busy_id, _ = await _seed_call(
        factory, storage, tmp_path, started_at=datetime(2000, 1, 2, tzinfo=UTC), suffix="f"
    )
    async with factory() as session:
        busy = await session.get(Call, busy_id)
        assert busy is not None
        busy.state = "isleniyor"  # işlenmekte olan süresi dolsa da silinmez
        await session.commit()

    # `now` 2001-06-01: 365 günlük süre için sınır 2000-06-01 olur; gerçek veriye dokunulmaz.
    summary = await purge_expired_calls(
        factory, storage, retention_days=365, batch_size=50, now=datetime(2001, 6, 1, tzinfo=UTC)
    )

    assert summary["silinen"] == 1 and summary["hata"] == 0
    present = {
        row[0]
        for row in (
            await conn.execute(
                text("SELECT id FROM calls WHERE id = ANY(:ids)"),
                {"ids": [old_id, new_id, busy_id]},
            )
        ).all()
    }
    assert present == {new_id, busy_id}
    assert not (tmp_path / "silme-testi-d.wav").exists()
    assert (tmp_path / "silme-testi-e.wav").exists()
    audit = await _count(
        conn,
        "SELECT count(*) FROM audit_log WHERE action = 'cagri_silindi' AND target_id = :t"
        " AND details->>'neden' = 'saklama_suresi'",
        t=str(old_id),
    )
    assert audit == 1
    assert (
        await _count(conn, "SELECT count(*) FROM audit_log WHERE target_id = :t", t=str(new_id))
        == 0
    )

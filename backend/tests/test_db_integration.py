"""Gerçek PostgreSQL (pgvector) ile şema testleri.

Yalnızca `RUN_DB_TESTS=1` iken çalışır (CI'daki duman testi işinde, migration uygulandıktan
sonra). Yerelde: `docker compose -f infra/docker-compose.yml up -d`, `alembic upgrade head`,
ardından `RUN_DB_TESTS=1 uv run pytest tests/test_db_integration.py`.

Her test kendi işleminde çalışır ve sonunda geri alınır; veritabanında iz bırakmaz.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import Settings

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


async def insert(conn: AsyncConnection, sql: str, **params: object) -> UUID:
    result = await conn.execute(text(sql + " RETURNING id"), params)
    value: UUID = result.scalar_one()
    return value


async def owner_with_boat(conn: AsyncConnection, name: str) -> tuple[UUID, UUID]:
    owner = await insert(conn, "INSERT INTO customers (full_name) VALUES (:n)", n=name)
    boat = await insert(
        conn, "INSERT INTO boats (owner_id, name) VALUES (:o, :b)", o=owner, b=f"{name} teknesi"
    )
    return owner, boat


async def test_full_analysis_row_with_agent_runs(conn: AsyncConnection) -> None:
    owner, boat = await owner_with_boat(conn, "Test Sahibi")
    call = await insert(
        conn,
        "INSERT INTO calls (started_at, answer_delay_s, switchboard_outcome, customer_id, boat_id)"
        " VALUES (:t, 7, 'randevu_olusturuldu', :c, :b)",
        t=datetime(2026, 10, 5, 9, 12, tzinfo=UTC),
        c=owner,
        b=boat,
    )
    analysis = await insert(
        conn,
        "INSERT INTO analysis_results (call_id, status, call_type, request_category, urgency,"
        " next_action, sales_outcome, crm_evidence, key_points)"
        " VALUES (:c, 'tamam', 'servis', 'makine', 'yuksek', 'servis_randevusu_olustur',"
        " 'satisa_donustu', CAST(:e AS jsonb), CAST(:k AS jsonb))",
        c=call,
        e='{"location": "Tuzla Marina\'da teknem var"}',
        k='["Motor devir sorunu"]',
    )
    await conn.execute(
        text(
            "INSERT INTO agent_runs (analysis_id, agent_name, status, attempts, model)"
            " VALUES (:a, 'crm_extraction', 'ok', 1, 'gemini-3.5-flash')"
        ),
        {"a": analysis},
    )

    row = (
        await conn.execute(
            text("SELECT version, crm_evidence->>'location' FROM analysis_results WHERE id = :a"),
            {"a": analysis},
        )
    ).one()
    assert row == (1, "Tuzla Marina'da teknem var")


@pytest.mark.parametrize(
    "bad_sql",
    [
        # Enum dışı kategori
        "INSERT INTO analysis_results (call_id, status, request_category) VALUES (:c, 'tamam', 'motor_arizasi')",
        # Kayıp nedeni ama satış kaybedilmemiş
        "INSERT INTO analysis_results (call_id, status, sales_outcome, loss_reason) VALUES (:c, 'tamam', 'satisa_donustu', 'fiyat')",
        # Kaybedildi ama neden yok
        "INSERT INTO analysis_results (call_id, status, sales_outcome) VALUES (:c, 'kismi', 'kaybedildi')",
        # Güven 0-1 dışında
        "INSERT INTO analysis_results (call_id, status, call_type_confidence) VALUES (:c, 'tamam', 1.5)",
        # Geçersiz analiz durumu
        "INSERT INTO analysis_results (call_id, status) VALUES (:c, 'bitti')",
    ],
)
async def test_check_constraints_reject_invalid_rows(conn: AsyncConnection, bad_sql: str) -> None:
    call = await insert(conn, "INSERT INTO calls (started_at) VALUES (now())")
    savepoint = await conn.begin_nested()

    with pytest.raises(IntegrityError):
        await conn.execute(text(bad_sql), {"c": call})
    await savepoint.rollback()


async def test_service_order_defaults_and_status_check(conn: AsyncConnection) -> None:
    owner, boat = await owner_with_boat(conn, "Servis Sahibi")
    order = await insert(
        conn,
        "INSERT INTO service_orders (boat_id, customer_id, category) VALUES (:b, :c, 'makine')",
        b=boat,
        c=owner,
    )
    status = (
        await conn.execute(text("SELECT status FROM service_orders WHERE id = :o"), {"o": order})
    ).scalar_one()
    assert status == "yeni_atandi"

    savepoint = await conn.begin_nested()
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("UPDATE service_orders SET status = 'bekliyor' WHERE id = :o"), {"o": order}
        )
    await savepoint.rollback()


async def test_rag_chunks_vector_search_and_tsvector_scoped_by_owner(conn: AsyncConnection) -> None:
    owner_a, boat_a = await owner_with_boat(conn, "Sahip A")
    owner_b, boat_b = await owner_with_boat(conn, "Sahip B")
    vector_a = "[" + ",".join(["0.1"] * 1024) + "]"
    vector_b = "[" + ",".join(["0.9"] * 1023 + ["-0.9"]) + "]"
    for owner, boat, content, vec in [
        (owner_a, boat_a, "Yakıt filtresi değiştirildi, impeller yenilendi.", vector_a),
        (owner_b, boat_b, "Enjektörler temizlendi.", vector_b),
    ]:
        await conn.execute(
            text(
                "INSERT INTO rag_chunks (source_kind, source_id, boat_id, owner_id, content, embedding)"
                " VALUES ('boat_note', gen_random_uuid(), :b, :o, :t, CAST(:v AS vector))"
            ),
            {"b": boat, "o": owner, "t": content, "v": vec},
        )

    # Tam metin: veritabanı tsvector'ü içerikten üretir (Türkçe kök bulma ile).
    hits = (
        (
            await conn.execute(
                text(
                    "SELECT content FROM rag_chunks WHERE owner_id = :o"
                    " AND tsv @@ plainto_tsquery('turkish', 'filtre')"
                ),
                {"o": owner_a},
            )
        )
        .scalars()
        .all()
    )
    assert hits == ["Yakıt filtresi değiştirildi, impeller yenilendi."]

    # Vektör araması: sahibin filtresi, başka sahibin parçasını hiç döndürmez.
    nearest = (
        (
            await conn.execute(
                text(
                    "SELECT owner_id FROM rag_chunks WHERE owner_id = :o"
                    " ORDER BY embedding <=> CAST(:q AS vector) LIMIT 5"
                ),
                {"o": owner_a, "q": vector_b},
            )
        )
        .scalars()
        .all()
    )
    assert nearest == [owner_a]


async def test_chat_message_checks(conn: AsyncConnection) -> None:
    owner, _ = await owner_with_boat(conn, "Sohbet Sahibi")
    session = await insert(conn, "INSERT INTO chat_sessions (owner_id) VALUES (:o)", o=owner)
    await conn.execute(
        text(
            "INSERT INTO chat_messages (session_id, role, content, question_type, found)"
            " VALUES (:s, 'assistant', 'Bulamadım.', 'gecmis_oneri', false)"
        ),
        {"s": session},
    )
    savepoint = await conn.begin_nested()
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("INSERT INTO chat_messages (session_id, role, content) VALUES (:s, 'bot', 'x')"),
            {"s": session},
        )
    await savepoint.rollback()

"""Müşteri aramasının gerçek PostgreSQL'de davranışı (#209). Yalnızca `RUN_DB_TESTS=1` iken.

Her test dış işlemde çalışır ve geri alınır; veritabanına kalıcı bir şey yazılmaz. Test müşterileri
adlarında "Zzz" öneki taşır, böylece seed verisiyle karışmaz.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.services.customer_search import search_customers

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


async def add_customer(
    conn: AsyncConnection, name: str, phone: str | None, boats: list[tuple[str, str | None]]
) -> UUID:
    cid = (
        await conn.execute(
            text("INSERT INTO customers (full_name, phone) VALUES (:n, :p) RETURNING id"),
            {"n": name, "p": phone},
        )
    ).scalar_one()
    for boat_name, model in boats:
        await conn.execute(
            text("INSERT INTO boats (owner_id, name, model) VALUES (:o, :n, :m)"),
            {"o": cid, "n": boat_name, "m": model},
        )
    return UUID(str(cid))


@pytest.fixture
async def people(conn: AsyncConnection) -> dict[str, UUID]:
    return {
        "ismail": await add_customer(
            conn,
            "Zzz İsmail Çelik",
            "+90 532 123 45 67",
            [("Rüzgârgülü", "Beneteau 40"), ("Aba", None)],
        ),
        "isik": await add_customer(conn, "Zzz IŞIK Öztürk", "0 (533) 987-65-43", []),
        "ali": await add_customer(conn, "Zzz Ali-Veli Şahin", None, [("Poyraz", None)]),
    }


async def names(session: AsyncSession, query: str | None, limit: int = 50) -> list[str]:
    return [
        c.name for c in await search_customers(session, query, limit) if c.name.startswith("Zzz")
    ]


@pytest.mark.parametrize(
    "query",
    ["ismail", "İSMAİL", "ISMAIL", "çelik", "CELIK", "celik ismail", "zzz ismail çel"],
)
async def test_name_search_ignores_case_and_turkish_characters(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID], query: str
) -> None:
    async with factory() as session:
        assert await names(session, query) == ["Zzz İsmail Çelik"]


async def test_turkish_dotless_and_dotted_i(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await names(session, "isik ozturk") == ["Zzz IŞIK Öztürk"]
        assert await names(session, "IŞIK") == ["Zzz IŞIK Öztürk"]
        assert await names(session, "işık") == ["Zzz IŞIK Öztürk"]


async def test_punctuation_in_name_is_ignored(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await names(session, "ali veli") == ["Zzz Ali-Veli Şahin"]
        assert await names(session, "ali-veli sahin") == ["Zzz Ali-Veli Şahin"]


@pytest.mark.parametrize(
    "query", ["532 123", "5321234567", "+90 532 123 45 67", "0532-123-45-67", "123 45 67"]
)
async def test_phone_search_is_digit_based(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID], query: str
) -> None:
    async with factory() as session:
        assert await names(session, query) == ["Zzz İsmail Çelik"]


async def test_phone_with_other_formatting_matches(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await names(session, "533 987 65 43") == ["Zzz IŞIK Öztürk"]


async def test_short_digit_query_does_not_match_phones(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await names(session, "53") == []


async def test_boat_name_finds_owner_and_returns_all_boats(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        found = [
            c for c in await search_customers(session, "ruzgargulu", 50) if c.name.startswith("Zzz")
        ]

    assert [c.name for c in found] == ["Zzz İsmail Çelik"]
    assert [(b.name, b.model) for b in found[0].boats] == [
        ("Aba", None),
        ("Rüzgârgülü", "Beneteau 40"),
    ]
    assert found[0].id == people["ismail"]
    assert found[0].phone == "+90 532 123 45 67"


async def test_wildcards_are_literal(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await search_customers(session, "%") == []
        assert await search_customers(session, "_") == []
        assert await search_customers(session, "zzz _smail") == []


async def test_unsearchable_query_returns_empty(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await search_customers(session, "!!! ---") == []


async def test_empty_query_returns_first_customers_limited(
    conn: AsyncConnection, factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        first = await search_customers(session, None, 3)
        blank = await search_customers(session, "   ", 3)
        everyone = await search_customers(session, "", 50)

    assert len(first) == 3
    assert [c.id for c in first] == [c.id for c in blank] == [c.id for c in everyone][:3]
    # Sıra veritabanının ada göre sıralamasıdır (harmanlama Python'dan farklı olabilir).
    expected = (
        await conn.execute(text("SELECT full_name FROM customers ORDER BY full_name, id LIMIT 50"))
    ).scalars()
    assert [c.name for c in everyone] == list(expected)


async def test_limit_is_applied(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert len(await search_customers(session, "zzz", 2)) == 2


async def test_sql_injection_attempt_is_harmless(
    factory: async_sessionmaker[AsyncSession], people: dict[str, UUID]
) -> None:
    async with factory() as session:
        assert await search_customers(session, "'; DROP TABLE customers; --") == []
        assert len(await search_customers(session, "zzz", 5)) == 3  # tablo yerinde

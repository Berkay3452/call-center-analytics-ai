"""Hibrit arama ve indeksleme, gerçek PostgreSQL + pgvector üzerinde (#26).

Yalnızca `RUN_DB_TESTS=1` iken. Embedding için modelsiz `HashEmbedder` kullanılır (deterministik);
bge-m3 ile gerçek doğruluk `scripts/rag_eval.py` ile ölçülür. Testler geri alınan işlemde çalışır.
"""

import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.rag.embedders import HashEmbedder
from app.rag.indexer import index_chunks
from app.rag.search import hybrid_search

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

EMBEDDER = HashEmbedder(dim=1024)

NOTES = [
    (
        "Ana makine bakımı yapıldı, yakıt filtresi değiştirildi ve impeller yenilendi.",
        date(2026, 8, 15),
    ),
    ("Servis aküleri test edildi, iki akü yenilendi. Şarj regülatörü normal.", date(2026, 7, 2)),
    ("Klima deniz suyu süzgeci temizlendi, gaz basıncı tamamlandı.", date(2026, 6, 20)),
]


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        finally:
            await transaction.rollback()
    await engine.dispose()


async def scalar(session: AsyncSession, sql: str, **params: object) -> UUID:
    value: UUID = (await session.execute(text(sql + " RETURNING id"), params)).scalar_one()
    return value


async def owner_with_notes(session: AsyncSession, name: str, boat: str) -> UUID:
    owner = await scalar(session, "INSERT INTO customers (full_name) VALUES (:n)", n=name)
    boat_id = await scalar(
        session, "INSERT INTO boats (owner_id, name) VALUES (:o, :b)", o=owner, b=boat
    )
    for i, (content, on) in enumerate(NOTES):
        note = await scalar(
            session,
            "INSERT INTO boat_notes (boat_id, content, note_date) VALUES (:b, :c, :d)",
            b=boat_id,
            c=content,
            d=on,
        )
        await session.execute(
            text(
                "INSERT INTO rag_chunks (source_kind, source_id, boat_id, owner_id, chunk_index,"
                " content) VALUES ('boat_note', :s, :b, :o, :i, :c)"
            ),
            {"s": note, "b": boat_id, "o": owner, "i": i, "c": content},
        )
    return owner


async def test_index_fills_missing_vectors_only(session: AsyncSession) -> None:
    await owner_with_notes(session, "Sahip A", "Poyraz")
    before = await session.scalar(text("SELECT count(*) FROM rag_chunks WHERE embedding IS NULL"))

    first = await index_chunks(session, EMBEDDER)
    second = await index_chunks(session, EMBEDDER)

    assert first == before
    assert second == 0  # zaten vektörü olanlar atlanır
    assert (
        await session.scalar(text("SELECT count(*) FROM rag_chunks WHERE embedding IS NULL")) == 0
    )
    assert await index_chunks(session, EMBEDDER, reindex=True) >= 3


async def test_hybrid_search_finds_note_with_turkish_suffix(session: AsyncSession) -> None:
    owner = await owner_with_notes(session, "Sahip A", "Poyraz")
    await index_chunks(session, EMBEDDER)

    hits = await hybrid_search(session, EMBEDDER, owner, "Yakıt filtrem ne zaman değişti?")

    assert hits
    top = hits[0]
    assert "yakıt filtresi" in top.text
    assert top.text_match  # "filtrem" sorgusu "filtresi" notunu tam metinde buldu
    assert top.source.kind == "boat_note"
    assert top.source.date == date(2026, 8, 15)
    assert top.source.title == "15.08.2026 usta notu (Poyraz)"


async def test_text_only_and_vector_only_modes(session: AsyncSession) -> None:
    owner = await owner_with_notes(session, "Sahip A", "Poyraz")
    await index_chunks(session, EMBEDDER)

    text_hits = await hybrid_search(session, EMBEDDER, owner, "akü", mode="text")
    vector_hits = await hybrid_search(session, EMBEDDER, owner, "akü", mode="vector")

    assert text_hits
    assert all(h.text_match and h.similarity is None for h in text_hits)
    assert all(not h.text_match and h.similarity is not None for h in vector_hits)


async def test_search_never_returns_other_owners_notes(session: AsyncSession) -> None:
    owner_a = await owner_with_notes(session, "Sahip A", "Poyraz")
    owner_b = await owner_with_notes(session, "Sahip B", "Rüzgar")
    await index_chunks(session, EMBEDDER)

    hits = await hybrid_search(session, EMBEDDER, owner_a, "akü klima yakıt filtresi", limit=10)

    assert len(hits) == 3  # yalnızca kendi üç notu
    own_sources = {
        str(r)
        for r in (
            await session.execute(
                text("SELECT source_id FROM rag_chunks WHERE owner_id = :o"), {"o": owner_a}
            )
        ).scalars()
    }
    assert {h.source.record_id for h in hits} <= own_sources
    assert all("Rüzgar" not in h.source.title for h in hits)
    assert owner_b != owner_a


async def test_unrelated_question_returns_nothing_with_threshold(session: AsyncSession) -> None:
    owner = await owner_with_notes(session, "Sahip A", "Poyraz")
    await index_chunks(session, EMBEDDER)

    hits = await hybrid_search(
        session, EMBEDDER, owner, "Yarın hava yağmurlu mu olacak?", min_similarity=0.5
    )

    assert hits == []


async def test_empty_question_returns_nothing(session: AsyncSession) -> None:
    owner = await owner_with_notes(session, "Sahip A", "Poyraz")

    assert await hybrid_search(session, EMBEDDER, owner, "   ") == []

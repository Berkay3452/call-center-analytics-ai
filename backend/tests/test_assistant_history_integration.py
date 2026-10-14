"""Miço AI geçmiş/öneri soruları, gerçek PostgreSQL + hibrit arama üzerinde (#50).

Yalnızca `RUN_DB_TESTS=1` iken. Seed verisi yüklü olmalıdır. Embedding için modelsiz
`HashEmbedder` kullanılır; LLM sahtedir. Testler geri alınan işlemde çalışır.
"""

import json
import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.assistant import retrieval
from app.assistant.assistant import answer_question
from app.assistant.llm import AssistantLLM
from app.assistant.retrieval import search_boat_notes
from app.core.config import Settings
from app.rag.embedders import HashEmbedder
from app.rag.indexer import index_chunks
from app.schemas.assistant import AssistantRequest, QuestionType
from tests.llm_fakes import scripted

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

OWNER_A = UUID("606bd734-644f-5c21-af2f-dc734c4ecd67")  # Ahmet Yılmaz
OWNER_B = UUID("cb138ca4-1453-5ef6-9537-713c5b7ecb4f")
EMBEDDER = HashEmbedder(dim=1024)
QUESTION = "Yakıt filtresi için usta ne önermişti?"


@pytest.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    monkeypatch.setattr(retrieval, "build_embedder", lambda settings: EMBEDDER)
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            async with factory() as s:
                await index_chunks(s, EMBEDDER)
                yield s
        finally:
            await transaction.rollback()
    await engine.dispose()


async def chunk_source_ids(session: AsyncSession, owner: UUID) -> set[str]:
    rows = await session.execute(
        text("SELECT source_id::text FROM rag_chunks WHERE owner_id = :o"), {"o": owner}
    )
    return {r[0] for r in rows}


async def test_search_returns_only_own_records(session: AsyncSession) -> None:
    own = await chunk_source_ids(session, OWNER_A)
    other = await chunk_source_ids(session, OWNER_B)
    assert own and other and not own & other

    for owner, allowed in ((OWNER_A, own), (OWNER_B, other)):
        hits = await search_boat_notes(str(owner), QUESTION, session=session)
        assert {h.source.record_id for h in hits} <= allowed


async def test_unknown_or_non_uuid_owner_gets_nothing(session: AsyncSession) -> None:
    assert await search_boat_notes("owner-yok", QUESTION, session=session) == []
    random_owner = "11111111-1111-1111-1111-111111111111"
    assert await search_boat_notes(random_owner, QUESTION, session=session) == []


async def test_history_answer_is_grounded_in_real_records(session: AsyncSession) -> None:
    hits = await search_boat_notes(str(OWNER_A), QUESTION, session=session)
    assert hits, "seed verisinde yakıt filtresiyle ilgili kayıt bulunmalı"
    source_id = hits[0].source.record_id
    draft = json.dumps(
        {
            "claims": [
                {
                    "text": "Kayıtlarda yakıt filtresiyle ilgili bir not var.",
                    "source_ids": [source_id],
                },
                {"text": "Ayrıca ücretsiz yağ değişimi hakkınız var.", "source_ids": []},
            ]
        },
        ensure_ascii=False,
    )
    model = scripted('{"question_type": "gecmis_oneri", "tool": null}', draft)

    answer = await answer_question(
        AssistantRequest(owner_id=str(OWNER_A), question=QUESTION),
        llm=AssistantLLM(model=model),
        session=session,
    )

    assert answer.found and answer.question_type == QuestionType.GECMIS_ONERI
    assert answer.answer == "Kayıtlarda yakıt filtresiyle ilgili bir not var."
    assert [s.record_id for s in answer.sources] == [source_id]
    assert "ücretsiz" not in answer.answer  # kaynaksız iddia düşürüldü


async def test_history_question_cannot_cite_other_owners_notes(session: AsyncSession) -> None:
    other = await chunk_source_ids(session, OWNER_B)
    hits = await search_boat_notes(str(OWNER_A), QUESTION, session=session)
    assert not {h.source.record_id for h in hits} & other

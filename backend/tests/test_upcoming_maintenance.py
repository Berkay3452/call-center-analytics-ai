"""Miço AI yaklaşan bakım (#125): kurallar, planlayıcı yönlendirmesi ve gerçek veritabanı.

Kural ve planlayıcı testleri her zaman çalışır; veritabanı testleri yalnızca `RUN_DB_TESTS=1`.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.assistant import tools
from app.assistant.answer import NO_UPCOMING_MESSAGE
from app.assistant.assistant import answer_question
from app.assistant.llm import AssistantLLM
from app.assistant.planner import plan_by_rules
from app.assistant.tools import add_months, note_recommendation
from app.core.config import Settings
from app.db.models.external import BoatNote, ServiceOrder, Subscription
from app.schemas.assistant import AssistantRequest, AssistantTool, QuestionType
from tests.llm_fakes import scripted

needs_db = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="RUN_DB_TESTS=1 değil (gerçek veritabanı gerekir)"
)

AHMET_ID = UUID("606bd734-644f-5c21-af2f-dc734c4ecd67")  # Poyraz, Yelkovan
POYRAZ_ID = UUID("289ee4a4-2598-5e69-8907-b044be2f85e5")
FATMA_ID = UUID("8ff32870-b5ca-5689-a6af-3548246f014e")  # Albatros, Kutup
BURAK_ID = UUID("c57e2519-87f4-597e-be0c-80889768255a")  # Rüzgar, Yakamoz
TODAY = date(2026, 10, 20)


# --- Kurallar (veritabanı yok) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 8, 15), 6, date(2027, 2, 15)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),  # ay sonu taşmaz
        (date(2025, 10, 20), 12, date(2026, 10, 20)),
    ],
)
def test_add_months(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


@pytest.mark.parametrize(
    ("text", "due"),
    [
        (
            "Ana makine bakımı tamamlandı. Altı ay sonra yakıt filtresi kontrolü önerilir.",
            date(2027, 2, 15),
        ),
        ("Yakıt filtresi değişti, 6 ay sonra tekrar kontrol önerilir.", date(2027, 2, 15)),
        ("Kelepçeler yenilendi, 2 yıl sonra körük değişmeli.", date(2028, 8, 15)),
    ],
)
def test_note_recommendation_extracts_date(text: str, due: date) -> None:
    found = note_recommendation(text, date(2026, 8, 15))

    assert found is not None
    assert found[1] == due


def test_note_without_period_gives_nothing() -> None:
    assert (
        note_recommendation("Akü değişti, sezon sonunda kontrol edilmeli.", date(2026, 3, 10))
        is None
    )


@pytest.mark.parametrize(
    "question",
    [
        "Yakında yapılması gereken bir şey var mı?",
        "Yaklaşan bakımlarım neler?",
        "Teknem için planlı bir iş var mı?",
        "Önümüzdeki dönemde yapmam gereken bakım var mı yakında?",
    ],
)
def test_planner_routes_upcoming_questions_without_llm(question: str) -> None:
    plan = plan_by_rules(question)

    assert plan is not None
    assert plan.tool == AssistantTool.GET_UPCOMING_MAINTENANCE


# --- Gerçek veritabanı --------------------------------------------------------------------------


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as conn:
        tx = await conn.begin()
        factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            async with factory() as s:
                yield s
        finally:
            await tx.rollback()
    await engine.dispose()


async def _clear(session: AsyncSession, owner: UUID) -> None:
    """Sahibin planlı işlerini sıfırlar: kural testleri kendi kaydını ekler."""
    from sqlalchemy import delete, select

    from app.db.models.external import Boat

    boat_ids = select(Boat.id).where(Boat.owner_id == owner).scalar_subquery()
    await session.execute(delete(BoatNote).where(BoatNote.boat_id.in_(boat_ids)))
    await session.execute(
        ServiceOrder.__table__.update()
        .where(ServiceOrder.boat_id.in_(boat_ids))
        .values(status="tamamlandi", category="diger")
    )
    await session.execute(
        Subscription.__table__.update()
        .where(Subscription.customer_id == owner)
        .values(expires_at=date(2030, 1, 1))
    )


@needs_db
async def test_seed_owner_gets_note_recommendation_with_source(session: AsyncSession) -> None:
    items = await tools.get_upcoming_maintenance(str(AHMET_ID), today=TODAY, session=session)

    fuel = [i for i in items if "yakıt filtresi" in i.what.casefold()]
    assert fuel, [i.what for i in items]
    assert fuel[0].boat_name == "Poyraz"
    assert fuel[0].due_on == date(2027, 2, 15)
    assert fuel[0].sources[0].kind == "boat_note"


@needs_db
async def test_owners_never_see_each_others_items(session: AsyncSession) -> None:
    ahmet = await tools.get_upcoming_maintenance(str(AHMET_ID), today=TODAY, session=session)
    fatma = await tools.get_upcoming_maintenance(str(FATMA_ID), today=TODAY, session=session)

    ahmet_ids = {s.record_id for i in ahmet for s in i.sources}
    fatma_ids = {s.record_id for i in fatma for s in i.sources}
    assert ahmet_ids and fatma_ids
    assert not ahmet_ids & fatma_ids
    assert {i.boat_name for i in fatma} <= {"Albatros", "Kutup"}


@needs_db
async def test_rules_cover_periodic_overdue_open_order_and_expiring_package(
    session: AsyncSession,
) -> None:
    await _clear(session, AHMET_ID)
    now = datetime(2025, 10, 1, 12, tzinfo=UTC)
    session.add_all(
        [
            # Yıllık motor bakımı 1 Ekim 2025'te yapılmış → 1 Ekim 2026'da gecikmiş.
            ServiceOrder(
                id=uuid4(), boat_id=POYRAZ_ID, customer_id=AHMET_ID, status="tamamlandi",
                category="makine", description="Yıllık motor bakımı", completed_at=now,
            ),
            # Planlanmış açık iş.
            ServiceOrder(
                id=uuid4(), boat_id=POYRAZ_ID, customer_id=AHMET_ID, status="onaylandi",
                category="temizlik_bakim", description="Pasta cila",
                scheduled_at=datetime(2026, 11, 3, 9, tzinfo=UTC),
            ),
            # Çok eski öneri: pencerenin dışında, listelenmez.
            BoatNote(
                id=uuid4(), boat_id=POYRAZ_ID, content="Bir yıl sonra boya kontrolü.",
                note_date=date(2024, 1, 1),
            ),
        ]
    )  # fmt: skip
    sub = Subscription(
        id=uuid4(), customer_id=AHMET_ID, plan_name="Test", total_services=2, used_services=1,
        expires_at=date(2026, 11, 5),
    )  # fmt: skip
    session.add(sub)
    await session.flush()

    items = await tools.get_upcoming_maintenance(str(AHMET_ID), today=TODAY, session=session)
    by_what = {i.what: i for i in items}

    periodic = by_what["Ana makine yıllık periyodik bakımı"]
    assert periodic.overdue and periodic.due_on == date(2026, 10, 1)
    assert by_what["Pasta cila"].due_on == date(2026, 11, 3)
    assert by_what["Test paketinin yenilenmesi"].due_on == date(2026, 11, 5)
    assert not any("boya" in w for w in by_what)
    assert [i.due_on for i in items] == sorted(i.due_on for i in items if i.due_on)


@needs_db
async def test_answer_lists_items_with_sources_and_no_llm(session: AsyncSession) -> None:
    model = scripted()  # LLM çağrılmamalı
    answer = await answer_question(
        AssistantRequest(
            question="Yakında yapılması gereken bir şey var mı?", owner_id=str(AHMET_ID)
        ),
        llm=AssistantLLM(model=model),
        today=TODAY,
        session=session,
    )

    assert answer.found and answer.question_type == QuestionType.SAYISAL
    assert "Poyraz" in answer.answer and "15 Şubat 2027" in answer.answer
    assert answer.sources
    assert model.calls == []


@needs_db
async def test_nothing_planned_says_so_clearly(session: AsyncSession) -> None:
    await _clear(session, BURAK_ID)

    answer = await answer_question(
        AssistantRequest(question="Yaklaşan bakımlarım neler?", owner_id=str(BURAK_ID)),
        llm=AssistantLLM(model=scripted()),
        today=TODAY,
        session=session,
    )

    assert not answer.found
    assert answer.answer == NO_UPCOMING_MESSAGE
    assert answer.sources == []


@needs_db
async def test_unknown_owner_gets_nothing(session: AsyncSession) -> None:
    assert await tools.get_upcoming_maintenance(str(uuid4()), today=TODAY, session=session) == []
    assert await tools.get_upcoming_maintenance("sahip-yok", today=TODAY, session=session) == []

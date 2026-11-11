"""Miço AI tekne adı çözümleme: birden fazla teknesi olan sahip (Poyraz + Yelkovan).

Sorulan tekneye daraltma, başkasının teknesini reddetme ve cevapta tekne adını söyleme.
"""

from datetime import date

import pytest

from app.assistant.assistant import answer_question
from app.assistant.boats import mentions_name, resolve_boat
from app.assistant.llm import AssistantLLM
from app.assistant.tools import BoatRef
from app.schemas.assistant import AssistantRequest, QuestionType
from tests import assistant_fakes
from tests.llm_fakes import scripted

OWNER = "owner-003"
TODAY = date(2026, 10, 12)
OWN = [BoatRef("boat-031", "Poyraz"), BoatRef("boat-032", "Yelkovan")]


@pytest.fixture(autouse=True)
def offline_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    assistant_fakes.install(monkeypatch)


async def ask(question: str, owner: str = OWNER):
    llm = AssistantLLM(model=scripted())  # kural yolu: LLM çağrılırsa AssertionError
    return await answer_question(
        AssistantRequest(question=question, owner_id=owner), llm=llm, today=TODAY
    )


@pytest.mark.parametrize(
    ("question", "name", "expected"),
    [
        ("Yelkovan teknesinin giderleri", "yelkovan", True),
        ("Yelkovan'ın son bakımı", "yelkovan", True),
        ("Yelkovanın giderleri", "yelkovan", True),
        ("gulet yelkovan", "yelkovan", True),
        ("Mavi Yelken teknem", "mavi yelken", True),
        ("Mavi bir tekne", "mavi yelken", False),
    ],
)
def test_mentions_name(question: str, name: str, expected: bool) -> None:
    from app.agents.grounding import normalize

    assert mentions_name(normalize(question), name) is expected


def test_resolve_picks_single_boat() -> None:
    match = resolve_boat("Yelkovan teknesinin giderleri", OWN, {"albatros"})
    assert match.boat == OWN[1] and not match.foreign


def test_resolve_both_boats_means_no_narrowing() -> None:
    match = resolve_boat("Poyraz ve Yelkovan giderleri", OWN, set())
    assert match.boat is None and not match.foreign


def test_resolve_foreign_boat() -> None:
    match = resolve_boat("Albatros teknesinin bakımı", OWN, {"albatros"})
    assert match.foreign and match.boat is None


def test_resolve_ignores_own_name_in_other_names() -> None:
    # Başka sahipte de "Poyraz" adlı tekne olsa bile kendi teknem sayılır.
    match = resolve_boat("Poyraz giderleri", OWN, {"poyraz"})
    assert match.boat == OWN[0] and not match.foreign


async def test_expense_total_narrowed_to_named_boat() -> None:
    answer = await ask("Yelkovan teknesinin giderleri ne kadar?")
    assert "Yelkovan teknesi için" in answer.answer
    assert "40.000" in answer.answer and "50.000" not in answer.answer


async def test_expense_total_without_boat_says_all_boats() -> None:
    answer = await ask("Toplam ne kadar harcadım?")
    assert "tüm teknelerinizde" in answer.answer
    assert "50.000" in answer.answer


async def test_single_boat_owner_text_unchanged() -> None:
    answer = await ask("Toplam ne kadar harcadım?", owner="owner-001")
    assert "tüm tekneler" not in answer.answer and "teknesi için" not in answer.answer


async def test_last_maintenance_for_named_boat() -> None:
    answer = await ask("Yelkovan teknesinin son bakımı ne zaman yapıldı?")
    assert "Yelkovan" in answer.answer and "Poyraz" not in answer.answer


async def test_job_expenses_narrowed() -> None:
    answer = await ask("Yelkovan jeneratör için ne kadar ödedim?")
    assert "Yelkovan" in answer.answer and "Poyraz" not in answer.answer


async def test_other_owners_boat_is_refused_with_own_boats_listed() -> None:
    answer = await ask("Albatros teknesinin bakım geçmişi nedir?")
    assert answer.question_type == QuestionType.KAPSAM_DISI
    assert "hesabınızda görünmüyor" in answer.answer
    assert "Poyraz" in answer.answer and "Yelkovan" in answer.answer
    assert "Beneteau" not in answer.answer  # başka sahibin verisi sızmaz


async def test_history_search_is_narrowed_to_boat(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    real = assistant_fakes.search_boat_notes

    async def spy(owner_id: str, query: str, **kw: object):
        seen["boat_id"] = kw.get("boat_id")
        return await real(owner_id, query, **kw)  # type: ignore[arg-type]

    from app.assistant import assistant as assistant_module

    monkeypatch.setattr(assistant_module, "search_boat_notes", spy)
    llm = AssistantLLM(
        model=scripted('{"question_type":"gecmis_oneri"}', '{"claims":[]}', '{"answer":"x"}')
    )
    await answer_question(
        AssistantRequest(question="Yelkovan jeneratörü için usta ne demişti?", owner_id=OWNER),
        llm=llm,
        today=TODAY,
    )
    assert seen["boat_id"] == "boat-032"


def test_without_boat_name_strips_name_and_suffix() -> None:
    from app.assistant.answer import without_boat_name

    boat = BoatRef("b", "Yelkovan")
    assert without_boat_name("Yelkovan'ın motor yağı?", boat) == "teknem motor yağı?"
    assert without_boat_name("Yelkovan motor yağı?", boat) == "teknem motor yağı?"
    assert without_boat_name("Motor yağı?", None) == "Motor yağı?"

"""Miço AI çok turlu bağlam (#111): takip sorusunu bağımsız soruya çevirme. LLM sahtedir."""

import json
from datetime import date

import pytest

from app.assistant.assistant import answer_question
from app.assistant.llm import AssistantLLM
from app.assistant.rewrite import looks_like_follow_up, standalone_question
from app.schemas.assistant import AssistantRequest, HistoryTurn, QuestionType
from tests import assistant_fakes
from tests.llm_fakes import ScriptedChatModel, scripted

OWNER_A = "owner-001"
OWNER_B = "owner-002"
TODAY = date(2026, 10, 12)


@pytest.fixture(autouse=True)
def offline_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    assistant_fakes.install(monkeypatch)


def turns(*pairs: tuple[str, str]) -> list[HistoryTurn]:
    return [HistoryTurn(role=role, content=text) for role, text in pairs]


HISTORY = turns(
    ("user", "Son bakım ne zaman yapıldı?"),
    ("assistant", "Poyraz için son bakım 15 Ağustos 2026 tarihinde yapıldı: Yakıt filtresi."),
)


def rewrite_json(text: str) -> str:
    return json.dumps({"standalone_question": text}, ensure_ascii=False)


def llm_with(*responses: str | Exception) -> tuple[AssistantLLM, ScriptedChatModel]:
    model = scripted(*responses)
    return AssistantLLM(model=model), model


# --- Kurallı kısa yol ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Peki ne yapılmıştı?",
        "Bu ayki?",
        "Ya geçen ay?",
        "Onun garantisi var mı?",
        "Neden?",
        "Usta ne önermişti?",
    ],
)
def test_follow_up_questions_are_detected(question: str) -> None:
    assert looks_like_follow_up(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "Bu ay ne kadar harcadım?",  # net sayısal: kural yakalar
        "Kaç bakım hakkım kaldı?",
        "Akü ne zaman değişti?",  # kısa ama konusu belli
        "Yakıt filtresi için usta ne önermişti?",
        "Jeneratör garantisi var mı?",
        "Teknemin motorunda geçen yıl yaşanan arıza hakkında usta notları neler?",  # uzun
    ],
)
def test_standalone_questions_skip_rewrite(question: str) -> None:
    assert looks_like_follow_up(question) is False


# --- Yeniden yazım ------------------------------------------------------------------------------


async def test_follow_up_is_rewritten_using_history() -> None:
    llm, model = llm_with(rewrite_json("15 Ağustos 2026'daki bakımda ne yapılmıştı?"))

    result = await standalone_question("Peki ne yapılmıştı?", HISTORY, llm)

    assert result == "15 Ağustos 2026'daki bakımda ne yapılmıştı?"
    assert "15 Ağustos 2026" in model.last_user  # geçmiş LLM'e verildi
    assert "Peki ne yapılmıştı?" in model.last_user


async def test_no_history_means_no_llm_call() -> None:
    llm, model = llm_with()

    assert await standalone_question("Peki ne yapılmıştı?", [], llm) == "Peki ne yapılmıştı?"
    assert model.calls == []


async def test_standalone_question_adds_no_llm_call() -> None:
    llm, model = llm_with()

    result = await standalone_question("Akü ne zaman değişti?", HISTORY, llm)

    assert result == "Akü ne zaman değişti?"
    assert model.calls == []


async def test_rewrite_failure_falls_back_to_original_question() -> None:
    llm, _ = llm_with(TimeoutError())

    assert await standalone_question("Peki ne yapılmıştı?", HISTORY, llm) == "Peki ne yapılmıştı?"


async def test_history_is_limited_and_truncated() -> None:
    long_history = turns(*[("user", "x" * 2000)] * 10)
    llm, model = llm_with(rewrite_json("Soru"))

    await standalone_question("Peki?", long_history, llm)

    assert model.last_user.count("Tekne sahibi:") == 6
    assert "x" * 401 not in model.last_user


# --- Uçtan uca takip senaryoları ----------------------------------------------------------------


def request(question: str, history: list[HistoryTurn], owner: str = OWNER_A) -> AssistantRequest:
    return AssistantRequest(question=question, owner_id=owner, history=history)


async def test_numeric_follow_up_uses_rewritten_question_for_planning() -> None:
    history = turns(
        ("user", "Toplam ne kadar harcadım?"), ("assistant", "Kayıtlı tüm dönemde toplam ...")
    )
    llm, model = llm_with(rewrite_json("Bu ay ne kadar harcadım?"))

    answer = await answer_question(request("Peki bu ayki?", history), llm=llm, today=TODAY)

    # Yeniden yazılan soru kurallarla sayısal sınıflandı: yalnızca 1 LLM çağrısı (yeniden yazım).
    assert len(model.calls) == 1
    assert answer.question_type == QuestionType.SAYISAL
    assert "Ekim 2026 döneminde" in answer.answer or not answer.found


async def test_history_follow_up_searches_with_rewritten_question() -> None:
    draft = json.dumps(
        {
            "claims": [
                {
                    "text": "Usta, altı ay sonra yakıt filtresi kontrolü önermiş.",
                    "source_ids": ["note-101"],
                }
            ]
        },
        ensure_ascii=False,
    )
    history = turns(
        ("user", "Yakıt filtresi ne zaman değişti?"), ("assistant", "15 Ağustos 2026'da.")
    )
    llm, model = llm_with(
        rewrite_json("Yakıt filtresi için usta ne önermişti?"),
        '{"question_type": "gecmis_oneri", "tool": null}',
        draft,
    )

    answer = await answer_question(request("Peki usta ne önermişti?", history), llm=llm)

    assert answer.found and [s.record_id for s in answer.sources] == ["note-101"]
    assert "Yakıt filtresi için usta ne önermişti?" in model.last_user  # cevap yeni soruyla


async def test_standalone_question_with_history_costs_no_extra_call() -> None:
    llm, model = llm_with()

    answer = await answer_question(
        request("Kaç bakım hakkım kaldı?", HISTORY), llm=llm, today=TODAY
    )

    assert answer.question_type == QuestionType.SAYISAL
    assert model.calls == []


async def test_follow_up_never_leaks_other_owners_records() -> None:
    """Geçmiş ne derse desin arama ve araçlar yalnızca isteği yapan sahibin kayıtlarına bakar."""
    history = turns(("user", "Albatros'un impeller notu ne?"), ("assistant", "Albatros ..."))
    llm, model = llm_with(
        rewrite_json("Yakıt filtresi için usta ne önermişti?"),
        '{"question_type": "gecmis_oneri", "tool": null}',
        '{"claims": []}',
    )

    answer = await answer_question(request("Peki usta ne önermişti?", history, OWNER_B), llm=llm)

    assert "note-101" not in model.last_user  # OWNER_A'nın kaydı B'nin bağlamına girmez
    assert all(s.record_id != "note-101" for s in answer.sources)


def test_expense_question_about_a_specific_job_is_not_the_total() -> None:
    """ "Akü için ne kadar ödedim" tüm giderlerin toplamı değildir; kural yakalamaz, LLM'e kalır."""
    from app.assistant.planner import plan_by_rules

    assert plan_by_rules("Akü değişimi için ne kadar ödemiştim?") is None
    assert plan_by_rules("Toplam ne kadar harcadım?") is not None

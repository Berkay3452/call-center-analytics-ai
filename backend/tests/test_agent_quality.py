"""Analiz çıktısı kalitesi (#84): marina adı tutarlılığı ve özetteki teknik terim yazımı.

Gerçek LLM gerekmez; sahte modelle ajanların sonrası işlemesi denenir.
"""

import json

import pytest

from app.agents.base import CallInfo
from app.agents.crm_extraction import CrmExtractionAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.terms import fix_terms, same_place
from tests.llm_fakes import scripted
from tests.test_agents import CRM_JSON, tuzla_ctx


def crm_json(location: str | None) -> str:
    data = json.loads(CRM_JSON)
    data["location"] = location
    if location is None:
        data["evidence"].pop("location", None)
    return json.dumps(data, ensure_ascii=False)


# --- Terim düzeltmeleri ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wrong", "right"),
    [
        ("generatörünün çalışmadığını", "jeneratörünün çalışmadığını"),
        ("Generatör arızalı", "Jeneratör arızalı"),
        ("generator bakımı", "jeneratör bakımı"),
        ("empeller yenilendi", "impeller yenilendi"),
        ("sentine pompası", "sintine pompası"),
        ("Jeneratör ve impeller doğru yazılmış", "Jeneratör ve impeller doğru yazılmış"),
        ("Müşteri motor bakımı istedi.", "Müşteri motor bakımı istedi."),
    ],
)
def test_fix_terms(wrong: str, right: str) -> None:
    assert fix_terms(wrong) == right


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Kalamış", "Kalamış Marina", True),
        ("Göcek", "Göcek D-Marin", True),
        ("Tuzla", "Tuzla Marina / Tersaneler", True),
        ("Marmaris", "Marmaris Netsel Marina", True),
        ("Çeşme Marina", "Çeşme Marina", True),
        ("Bodrum", "Yalıkavak Marina", False),
        ("Marina", "Kalamış Marina", False),  # yalnızca genel kelime: aynı yer sayılmaz
        ("", "Kalamış Marina", False),
    ],
)
def test_same_place(a: str, b: str, expected: bool) -> None:
    assert same_place(a, b) is expected


# --- CRM: konum, santraldeki marina adıyla tutarlı ------------------------------------------


async def test_location_is_normalized_to_switchboard_marina() -> None:
    ctx = tuzla_ctx(call_info=CallInfo(marina="Tuzla Marina / Tersaneler"))

    result = await CrmExtractionAgent(model=scripted(crm_json("Tuzla Marina"))).run(ctx)

    assert result.status == "ok" and result.output is not None
    assert result.output.location == "Tuzla Marina / Tersaneler"
    assert "location" in result.output.evidence  # konuşmadaki alıntı korunur


async def test_location_is_filled_from_call_info_when_not_in_conversation() -> None:
    ctx = tuzla_ctx(call_info=CallInfo(marina="Kalamış Marina"))

    result = await CrmExtractionAgent(model=scripted(crm_json(None))).run(ctx)

    assert result.output is not None and result.output.location == "Kalamış Marina"
    assert "location" not in result.output.evidence  # konuşmada kanıt yok, uydurulmaz


async def test_different_place_in_conversation_is_not_overwritten() -> None:
    ctx = tuzla_ctx(call_info=CallInfo(marina="Yalıkavak Marina"))

    result = await CrmExtractionAgent(model=scripted(crm_json("Tuzla Marina"))).run(ctx)

    assert result.output is not None and result.output.location == "Tuzla Marina"


async def test_location_untouched_without_call_info_marina() -> None:
    result = await CrmExtractionAgent(model=scripted(crm_json("Tuzla Marina"))).run(tuzla_ctx())

    assert result.output is not None and result.output.location == "Tuzla Marina"
    info = tuzla_ctx().call_info
    assert info is not None and info.marina is None


def test_marina_is_shown_to_the_llm_in_call_info() -> None:
    agent = CrmExtractionAgent()
    message = agent._user_message(tuzla_ctx(call_info=CallInfo(marina="Kalamış Marina")))

    assert "Çağrı bilgisi" in message and "Kalamış Marina" in message


# --- Özet: teknik terimler düzeltilir -------------------------------------------------------


async def test_summary_terms_are_corrected() -> None:
    summary = json.dumps(
        {
            "summary": "Müşteri generatörünün çalışmadığını bildirdi.",
            "key_points": ["Generatör arızası", "Yarın yerinde servis"],
        },
        ensure_ascii=False,
    )

    result = await SummarizerAgent(model=scripted(summary)).run(tuzla_ctx())

    assert result.output is not None
    assert result.output.summary == "Müşteri jeneratörünün çalışmadığını bildirdi."
    assert result.output.key_points == ["Jeneratör arızası", "Yarın yerinde servis"]

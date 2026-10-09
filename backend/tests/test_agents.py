"""Analiz agent'larının testleri. LLM yerine `ScriptedChatModel` kullanılır.

Bu testler agent'ın mesajları doğru kurduğunu, cevabı doğru ayrıştırıp doğruladığını ve
hataları doğru sınıfladığını kanıtlar. Modelin Türkçe kalitesi burada değil, gerçek LLM ile
#21'deki uçtan uca değerlendirmede ölçülür.
"""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from app.agents.base import AnalysisContext, CallInfo, Segment
from app.agents.call_classifier import CallClassifierAgent
from app.agents.crm_extraction import CrmExtractionAgent
from app.agents.grounding import is_grounded, normalize, transcript_text
from app.agents.llm_agent import extract_json_object, format_transcript, load_prompt
from app.agents.names import CALL_CLASSIFIER, CRM_EXTRACTION, SALES_ANALYZER, SUMMARIZER
from app.agents.orchestrator import Orchestrator
from app.agents.registry import default_stages
from app.agents.sales_analyzer import SalesAnalyzerAgent
from app.agents.summarizer import SummarizerAgent, find_personal_data
from app.core.config import Settings
from app.domain.enums import (
    CallType,
    LossReason,
    NextAction,
    RequestCategory,
    SalesOutcomeType,
    ServiceMode,
    Urgency,
)
from app.schemas.analysis import CrmExtraction
from tests.llm_fakes import scripted

# Hocanın örnek senaryosu (Sistem mimarisi v3.1 §6.1).
TUZLA_SEGMENTS = [
    Segment(
        idx=0,
        speaker="customer",
        start_ms=0,
        end_ms=6000,
        text_masked=(
            "Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir "
            "yükselmiyor. Yarın bir usta gelebilir mi?"
        ),
    ),
    Segment(
        idx=1,
        speaker="rep",
        start_ms=6000,
        end_ms=9000,
        text_masked="Tabii [İSİM] Bey, yarın sabah için yerinde servis randevusu oluşturalım.",
    ),
]

CLASSIFICATION_JSON = json.dumps(
    {"call_type": "servis", "confidence": 0.93, "reason": "Arıza bildirip usta istiyor."},
    ensure_ascii=False,
)


def tuzla_ctx(**overrides: Any) -> AnalysisContext:
    data: dict[str, Any] = {
        "call_id": uuid4(),
        "segments": TUZLA_SEGMENTS,
        "call_info": CallInfo(answer_delay_s=8),
    }
    data.update(overrides)
    return AnalysisContext(**data)


# --- Yardımcı fonksiyonlar ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Tabii, işte sonuç:\n{"a": 1}\nUmarım yardımcı olur.',
    ],
)
def test_extract_json_object_handles_common_llm_wrappings(text: str) -> None:
    assert extract_json_object(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "JSON yok", "[1, 2]", '{"a": }'])
def test_extract_json_object_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        extract_json_object(text)


def test_transcript_uses_turkish_speaker_labels() -> None:
    text = format_transcript(TUZLA_SEGMENTS)

    assert text.startswith("[0] Müşteri: Merhaba")
    assert "[1] Firma: Tabii" in text


# --- LLMAgent tabanı (Çağrı Sınıflandırma üzerinden) ------------------------------------------


async def test_agent_builds_prompt_and_parses_output() -> None:
    model = scripted(CLASSIFICATION_JSON)
    agent = CallClassifierAgent(model=model)

    result = await agent.run(tuzla_ctx(prior={"onceki": {"x": 1}}))

    assert result.status == "ok"
    assert result.output is not None
    assert result.output.call_type == CallType.SERVIS
    assert (result.model, result.prompt_version) == ("sahte-model", "call_classifier.v1")
    assert (result.tokens_in, result.tokens_out) == (120, 30)
    # Sistem mesajı: ortak kurallar + agent'ın kendi talimatı.
    assert load_prompt("common").splitlines()[0] in model.last_system
    assert "ÇAĞRI TİPİNİ" in model.last_system
    # Kullanıcı mesajı: transkript, çağrı bilgisi, önceki çıktılar ve JSON şeması.
    user = model.last_user
    assert "Tuzla Marina'da teknem var" in user
    assert '"answer_delay_s": 8.0' in user
    assert '"onceki"' in user
    assert '"call_type"' in user and "yeni_musteri" in user


async def test_feedback_is_added_to_prompt() -> None:
    model = scripted(CLASSIFICATION_JSON)

    await CallClassifierAgent(model=model).run(tuzla_ctx(feedback="- call_type: geçersiz değer"))

    assert "Düzeltme gerekli" in model.last_user
    assert "- call_type: geçersiz değer" in model.last_user


async def test_invalid_json_is_validation_error() -> None:
    result = await CallClassifierAgent(model=scripted("Bu bir servis çağrısı.")).run(tuzla_ctx())

    assert (result.status, result.error_kind) == ("failed", "validation")
    assert "JSON" in (result.error or "")
    assert result.tokens_in == 120  # başarısız denemenin maliyeti de kaydedilir


async def test_schema_mismatch_gives_short_readable_error() -> None:
    bad = '{"call_type": "sikayet", "confidence": 1.5, "reason": "x"}'

    result = await CallClassifierAgent(model=scripted(bad)).run(tuzla_ctx())

    assert result.error_kind == "validation"
    error = result.error or ""
    assert error.startswith("Çıktı şemaya uymuyor")
    assert "- call_type:" in error and "- confidence:" in error
    assert "https://" not in error  # Pydantic'in uzun belge bağlantıları LLM'e gitmez


async def test_provider_error_is_runtime_error() -> None:
    model = scripted(ConnectionError("429 Too Many Requests"))

    result = await CallClassifierAgent(model=model).run(tuzla_ctx())

    assert (result.status, result.error_kind) == ("failed", "runtime")
    assert "429" in (result.error or "")


async def test_missing_llm_config_is_runtime_error(
    settings_factory: Callable[..., Settings],
) -> None:
    agent = CallClassifierAgent(settings=settings_factory(llm_fast_model=None))

    result = await agent.run(tuzla_ctx())

    assert (result.status, result.error_kind) == ("failed", "runtime")
    assert "LLM yapılandırılmadı" in (result.error or "")


async def test_orchestrator_fix_loop_with_real_agent() -> None:
    """Şemaya uymayan ilk cevaptan sonra hata mesajı geri verilir; ikinci cevap kabul edilir."""
    model = scripted(
        '{"call_type": "sikayet", "confidence": 0.9, "reason": "x"}', CLASSIFICATION_JSON
    )

    result = await Orchestrator([[CallClassifierAgent(model=model)]]).run(tuzla_ctx())

    assert result.status == "tamam"
    assert result.runs[0].attempts == 2
    assert result.runs[0].tokens_in == 240  # iki denemenin toplamı
    assert "- call_type:" in model.last_user  # ikinci denemede düzeltme mesajı vardı


# --- Çağrı Sınıflandırma (#17) ----------------------------------------------------------------


def test_call_classifier_contract() -> None:
    agent = CallClassifierAgent()

    assert agent.name == CALL_CLASSIFIER
    assert agent.model_tier == "fast"
    prompt = load_prompt(agent.prompt_file)
    # Prompt, şemadaki her çağrı tipini tanımlamalı.
    for call_type in CallType:
        assert f"- {call_type.value}:" in prompt


async def test_call_classifier_on_hoca_scenario() -> None:
    result = await CallClassifierAgent(model=scripted(CLASSIFICATION_JSON)).run(tuzla_ctx())

    assert result.status == "ok"
    assert result.output is not None
    assert result.output.call_type == CallType.SERVIS
    assert 0 <= result.output.confidence <= 1


# --- CRM Bilgi Çıkarım (#18) ------------------------------------------------------------------

CRM_JSON = json.dumps(
    {
        "request_category": "motor_arizasi",
        "location": "Tuzla Marina",
        "problem": "Motor gaz verince devir almıyor",
        "service_mode": "yerinde_servis",
        "urgency": "yuksek",
        "potential_job": "Motor arıza tespiti",
        "next_action": "servis_randevusu_olustur",
        "evidence": {
            "location": "Tuzla Marina'da teknem var",
            "problem": "gaz verdiğimde devir yükselmiyor",
        },
    },
    ensure_ascii=False,
)


def test_crm_extraction_contract() -> None:
    agent = CrmExtractionAgent()

    assert agent.name == CRM_EXTRACTION
    assert agent.model_tier == "smart"
    prompt = load_prompt(agent.prompt_file)
    # Prompt, CRM kaydının 7 alanını ve seçmeli alanların her değerini tanımlamalı.
    for field in CrmExtraction.model_fields:
        assert f"- {field}:" in prompt
    for enum_cls in (RequestCategory, ServiceMode, Urgency, NextAction):
        for member in enum_cls:
            assert f"- {member.value}:" in prompt, member


async def test_crm_extraction_on_hoca_scenario() -> None:
    """Hocanın örneğindeki 7 alanın tamamı."""
    result = await CrmExtractionAgent(model=scripted(CRM_JSON)).run(tuzla_ctx())

    assert result.status == "ok"
    crm = result.output
    assert crm is not None
    assert crm.request_category == RequestCategory.MOTOR_ARIZASI
    assert crm.location == "Tuzla Marina"
    assert crm.problem == "Motor gaz verince devir almıyor"
    assert crm.service_mode == ServiceMode.YERINDE_SERVIS
    assert crm.urgency == Urgency.YUKSEK
    assert crm.potential_job == "Motor arıza tespiti"
    assert crm.next_action == NextAction.SERVIS_RANDEVUSU_OLUSTUR
    assert set(crm.evidence) == {"location", "problem"}


async def test_crm_extraction_keeps_unknown_fields_null() -> None:
    sparse = '{"request_category": "motor_arizasi", "evidence": {}}'

    result = await CrmExtractionAgent(model=scripted(sparse)).run(tuzla_ctx())

    assert result.status == "ok"
    assert result.output is not None
    assert result.output.location is None
    assert result.output.next_action is None


async def test_crm_extraction_drops_ungrounded_and_orphan_evidence() -> None:
    answer = json.dumps(
        {
            "location": "Tuzla Marina",
            "problem": "Devir yükselmiyor",
            "evidence": {
                "location": "TUZLA MARINA'DA teknem var!",  # büyük harf/noktalama farkı: kalır
                "problem": "motor tamamen bozuldu",  # konuşmada geçmiyor: çıkar
                "urgency": "Yarın bir usta gelebilir mi",  # alan boş: çıkar
            },
        },
        ensure_ascii=False,
    )

    result = await CrmExtractionAgent(model=scripted(answer)).run(tuzla_ctx())

    assert result.status == "ok"
    assert result.output is not None
    assert result.output.evidence == {"location": "TUZLA MARINA'DA teknem var!"}
    assert result.output.problem == "Devir yükselmiyor"  # alanın kendisine dokunulmaz


async def test_crm_extraction_sees_classifier_output_in_pipeline() -> None:
    crm_model = scripted(CRM_JSON)
    orchestrator = Orchestrator(
        [
            [CallClassifierAgent(model=scripted(CLASSIFICATION_JSON))],
            [CrmExtractionAgent(model=crm_model)],
        ]
    )

    result = await orchestrator.run(tuzla_ctx())

    assert result.status == "tamam"
    assert '"call_type": "servis"' in crm_model.last_user
    analysis = result.to_analysis_result()
    assert analysis.crm is not None
    assert analysis.crm.location == "Tuzla Marina"


# --- Alıntı doğrulama ---------------------------------------------------------------------------


def test_normalize_ignores_case_punctuation_and_turkish_letters() -> None:
    assert normalize("  Tuzla Marina'da!  ") == "tuzla marina da"
    assert normalize("IŞIK, ışık; İğne") == normalize("isik isik igne")


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("gaz verdiğimde devir yükselmiyor", True),
        ("GAZ VERDIGIMDE DEVIR YUKSELMIYOR", True),
        ("devir yükselmiyor yarın", True),  # cümle sınırını aşan alıntı da olur
        ("devir yükselmedi", False),  # yeniden yazılmış
        ("az verdiğimde", False),  # kelime ortasından başlayan parça
        ("", False),
    ],
)
def test_is_grounded(quote: str, expected: bool) -> None:
    assert is_grounded(quote, transcript_text(TUZLA_SEGMENTS)) is expected


# --- Satış Analiz (#19) -----------------------------------------------------------------------

LOST_SEGMENTS = [
    Segment(
        idx=0,
        speaker="rep",
        start_ms=0,
        end_ms=4000,
        text_masked="Kış bakımı paketi için fiyatımız [TUTAR], sezon sonuna kadar geçerli.",
    ),
    Segment(
        idx=1,
        speaker="customer",
        start_ms=4000,
        end_ms=8000,
        text_masked="O fiyata olmaz, çok pahalı. Ben başka yere bakacağım.",
    ),
]


def test_sales_analyzer_contract() -> None:
    agent = SalesAnalyzerAgent()

    assert agent.name == SALES_ANALYZER
    assert agent.model_tier == "smart"
    prompt = load_prompt(agent.prompt_file)
    for enum_cls in (SalesOutcomeType, LossReason):
        for member in enum_cls:
            assert f"- {member.value}:" in prompt, member


async def test_sales_analyzer_lost_on_price() -> None:
    answer = json.dumps(
        {
            "outcome": "kaybedildi",
            "loss_reason": "fiyat",
            "evidence": "O fiyata olmaz, çok pahalı",
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = await SalesAnalyzerAgent(model=scripted(answer)).run(tuzla_ctx(segments=LOST_SEGMENTS))

    assert result.status == "ok"
    assert result.output is not None
    assert result.output.outcome == SalesOutcomeType.KAYBEDILDI
    assert result.output.loss_reason == LossReason.FIYAT
    assert result.output.evidence == "O fiyata olmaz, çok pahalı"


async def test_sales_analyzer_converted_on_hoca_scenario() -> None:
    answer = (
        '{"outcome": "satisa_donustu", "loss_reason": null, "evidence": null, "confidence": 0.8}'
    )

    result = await SalesAnalyzerAgent(model=scripted(answer)).run(tuzla_ctx())

    assert result.output is not None
    assert result.output.outcome == SalesOutcomeType.SATISA_DONUSTU
    assert result.output.loss_reason is None


async def test_sales_analyzer_rule_violation_gets_fixed_by_orchestrator() -> None:
    """Satışa dönüşmüş çağrıya kayıp nedeni yazılırsa şema reddeder, ikinci denemede düzelir."""
    wrong = '{"outcome": "satisa_donustu", "loss_reason": "fiyat", "confidence": 0.8}'
    right = '{"outcome": "satisa_donustu", "loss_reason": null, "confidence": 0.8}'
    model = scripted(wrong, right)

    result = await Orchestrator([[SalesAnalyzerAgent(model=model)]]).run(tuzla_ctx())

    assert result.status == "tamam"
    assert result.runs[0].attempts == 2
    assert "loss_reason yalnızca" in model.last_user


async def test_sales_analyzer_drops_ungrounded_evidence() -> None:
    answer = json.dumps(
        {
            "outcome": "kaybedildi",
            "loss_reason": "rakip",
            "evidence": "Rakip firma daha ucuza yapıyor",
            "confidence": 0.7,
        },
        ensure_ascii=False,
    )

    result = await SalesAnalyzerAgent(model=scripted(answer)).run(tuzla_ctx(segments=LOST_SEGMENTS))

    assert result.output is not None
    assert result.output.loss_reason == LossReason.RAKIP
    assert result.output.evidence is None


async def test_sales_analyzer_sees_switchboard_outcome() -> None:
    model = scripted('{"outcome": "beklemede", "confidence": 0.6}')

    await SalesAnalyzerAgent(model=model).run(tuzla_ctx(call_info=CallInfo(outcome="geri_ara")))

    assert '"outcome": "geri_ara"' in model.last_user


# --- Özetleme (#20) ---------------------------------------------------------------------------

SUMMARY_JSON = json.dumps(
    {
        "summary": (
            "Müşteri, Tuzla Marina'daki teknesinde gaz verildiğinde devrin yükselmediğini "
            "bildirdi. Firma ertesi sabah için yerinde servis randevusu oluşturdu."
        ),
        "key_points": ["Motor devir sorunu", "Tuzla Marina", "Yarın yerinde servis"],
    },
    ensure_ascii=False,
)


def test_summarizer_contract() -> None:
    agent = SummarizerAgent()

    assert agent.name == SUMMARIZER
    assert agent.model_tier == "fast"
    prompt = load_prompt(agent.prompt_file)
    assert "- summary:" in prompt and "- key_points:" in prompt


async def test_summarizer_on_hoca_scenario() -> None:
    result = await SummarizerAgent(model=scripted(SUMMARY_JSON)).run(tuzla_ctx())

    assert result.status == "ok"
    assert result.output is not None
    assert "Tuzla Marina" in result.output.summary
    assert len(result.output.key_points) == 3


async def test_summarizer_rejects_more_than_three_sentences() -> None:
    long = '{"summary": "Bir. İki. Üç. Dört.", "key_points": []}'

    result = await SummarizerAgent(model=scripted(long)).run(tuzla_ctx())

    assert result.error_kind == "validation"
    assert "3 cümle" in (result.error or "")


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Müşteri 0532 123 45 67 numarasından aradı.", "uzun numara"),
        ("Müşteri +90 (532) 123-45-67 numarasını verdi.", "uzun numara"),
        ("Kimlik no 12345678901 olarak paylaşıldı.", "uzun numara"),
        ("Fatura ornek.kisi@example.com adresine gidecek.", "e-posta"),
        ("Ödeme TR33 0006 1005 1978 6457 8413 26 hesabına yapılacak.", "IBAN"),
        ("[İSİM] Bey randevu istedi.", "maskeli ifade"),
    ],
)
def test_find_personal_data_detects_leaks(text: str, kind: str) -> None:
    assert any(kind in found for found in find_personal_data(text))


@pytest.mark.parametrize(
    "text",
    [
        "Müşteri 15.10.2026 14:30 için randevu aldı.",
        "Teknenin boyu 12 metre, motoru 2 x 250 beygir.",
        "Kış bakımı 12 500 TL olarak teklif edildi.",
    ],
)
def test_find_personal_data_ignores_business_numbers(text: str) -> None:
    assert find_personal_data(text) == []


async def test_summarizer_personal_data_leak_gets_fixed_by_orchestrator() -> None:
    leaked = '{"summary": "Müşteri 0532 123 45 67 numarasından aradı.", "key_points": []}'
    model = scripted(leaked, SUMMARY_JSON)

    result = await Orchestrator([[SummarizerAgent(model=model)]]).run(tuzla_ctx())

    assert result.status == "tamam"
    assert result.runs[0].attempts == 2
    assert "kişisel veri" in model.last_user


# --- Dört agent birlikte (varsayılan akış) ------------------------------------------------------


async def test_full_pipeline_on_hoca_scenario() -> None:
    """Varsayılan akıştaki dört agent, sahte LLM'lerle hocanın senaryosunu uçtan uca işler."""
    sales_json = '{"outcome": "satisa_donustu", "confidence": 0.85}'
    responses = {
        CALL_CLASSIFIER: CLASSIFICATION_JSON,
        CRM_EXTRACTION: CRM_JSON,
        SALES_ANALYZER: sales_json,
        SUMMARIZER: SUMMARY_JSON,
    }
    stages = default_stages()
    for stage in stages:
        for agent in stage:
            agent._model = scripted(responses[agent.name])  # type: ignore[attr-defined]

    result = await Orchestrator(stages).run(tuzla_ctx())
    analysis = result.to_analysis_result()

    assert analysis.status == "tamam"
    assert analysis.errors == {}
    assert analysis.classification is not None
    assert analysis.classification.call_type == CallType.SERVIS
    assert analysis.crm is not None
    assert analysis.crm.next_action == NextAction.SERVIS_RANDEVUSU_OLUSTUR
    assert analysis.sales is not None
    assert analysis.sales.outcome == SalesOutcomeType.SATISA_DONUSTU
    assert analysis.summary is not None
    assert [r.agent for r in analysis.runs] == [
        CALL_CLASSIFIER,
        CRM_EXTRACTION,
        SALES_ANALYZER,
        SUMMARIZER,
    ]

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
from app.agents.llm_agent import extract_json_object, format_transcript, load_prompt
from app.agents.names import CALL_CLASSIFIER
from app.agents.orchestrator import Orchestrator
from app.core.config import Settings
from app.domain.enums import CallType
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

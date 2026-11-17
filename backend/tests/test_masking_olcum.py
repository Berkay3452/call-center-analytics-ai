"""Maskeleme ölçümü ve ham kişisel verinin LLM/günlük/agent kayıtlarına sızmaması (#268).

Hepsi LLM'siz ve veritabansız çalışır (sahte sohbet modeli).
"""

import json
from typing import Any
from uuid import uuid4

import pytest
import structlog
from structlog.testing import capture_logs

from app.agents.base import AnalysisContext, Segment
from app.agents.call_classifier import CallClassifierAgent
from app.agents.summarizer import SummarizerAgent, find_personal_data
from app.services.masking import mask_text
from scripts.maskeleme_olcum import OLCUM_SETI, olc, sentetik_degisenler
from tests.llm_fakes import ScriptedChatModel

STRUCTURED = {"e-posta", "iban", "tc-kimlik", "telefon", "kart", "belge-no", "vergi-no", "plaka"}


def test_measurement_set_has_enough_labeled_sentences() -> None:
    assert len(OLCUM_SETI) >= 50


def test_structured_categories_recall_is_100_percent() -> None:
    sonuclar = olc(zor=False)

    for kategori in STRUCTURED:
        s = sonuclar[kategori]
        assert s.gizli_yakalanan == s.gizli_toplam, s.kacirilan


def test_every_category_recall_meets_95_percent_target() -> None:
    for s in olc(zor=False).values():
        if s.gizli_toplam:
            assert s.gizli_yakalanan / s.gizli_toplam >= 0.95, (s.kategori, s.kacirilan)


def test_no_false_masking_of_lookalike_text() -> None:
    for s in olc().values():
        assert s.korunan_bozulan == 0, s.bozulan


def test_synthetic_calls_are_not_altered_by_masking() -> None:
    """Sentetik çağrılarda gerçek kişisel veri yok; maskeleme hiçbir turu değiştirmemeli."""
    toplam, degisen = sentetik_degisenler()

    assert toplam > 1000
    assert degisen == []


@pytest.mark.parametrize(
    ("raw", "token"),
    [
        ("Kart 4539 1488 0343 6467 ile ödeyin", "[KART]"),
        ("Vergi no 1234567890", "[VERGİ_NO]"),
        ("Pasaport no U12345678", "[BELGE_NO]"),
        ("Plakası 34 ABC 123", "[PLAKA]"),
        ("Cumhuriyet Mahallesi 12. Sokak No 5", "[ADRES]"),
        ("Ben Mehmet Yıldız arıyorum", "[İSİM]"),
    ],
)
def test_new_categories_use_expected_tokens(raw: str, token: str) -> None:
    assert token in mask_text(raw)


def test_card_requires_valid_luhn_but_digits_are_still_masked() -> None:
    masked = mask_text("Numara 1234 5678 9012 3456 olsun")

    assert "[KART]" not in masked  # Luhn'u geçmez, kart sayılmaz
    assert "1234" not in masked  # ama uzun numara olarak (telefon) yine maskelenir


def test_place_after_ben_is_not_a_name() -> None:
    assert mask_text("Ben Tuzla Marina'dan arıyorum.") == "Ben Tuzla Marina'dan arıyorum."


# --- Ham veri LLM'e, günlüğe ve agent kayıtlarına gitmez ----------------------------------

RAW_TURNS = [
    ("customer", "Ben Mehmet Yıldız, 0532 123 45 67 numarasından arıyorum."),
    ("customer", "Mail adresim mehmet.yildiz@ornek.com, kartım 4539 1488 0343 6467."),
    ("rep", "Cumhuriyet Mahallesi 12. Sokak No 5 adresine usta gönderelim, plaka 34 ABC 123."),
    ("customer", "Kimlik 10000000146, vergi no 1234567890. Teknem Rüzgar, motor çalışmıyor."),
]
RAW_VALUES = [
    "Mehmet",
    "Yıldız",
    "0532 123 45 67",
    "mehmet.yildiz@ornek.com",
    "4539 1488 0343 6467",
    "Cumhuriyet",
    "34 ABC 123",
    "10000000146",
    "1234567890",
]


def _segments() -> list[Segment]:
    return [
        Segment(
            idx=i, speaker=sp, start_ms=i * 1000, end_ms=i * 1000 + 900, text_masked=mask_text(t)
        )  # type: ignore[arg-type]
        for i, (sp, t) in enumerate(RAW_TURNS)
    ]


def _assert_clean(blob: str) -> None:
    leaked = [v for v in RAW_VALUES if v in blob]
    assert leaked == [], f"ham kişisel veri sızdı: {leaked}"


async def test_llm_receives_only_masked_text_and_logs_stay_clean() -> None:
    structlog.reset_defaults()
    classifier_model = ScriptedChatModel(
        responses=[
            json.dumps({"call_type": "servis", "confidence": 0.9, "reason": "Arıza bildirimi."})
        ]
    )
    summary_model = ScriptedChatModel(
        responses=[
            json.dumps({"summary": "Müşteri motor arızası bildirdi.", "key_points": ["Motor"]})
        ]
    )
    ctx = AnalysisContext(call_id=uuid4(), segments=_segments())

    with capture_logs() as logs:
        results = [
            await CallClassifierAgent(model=classifier_model).run(ctx),
            await SummarizerAgent(model=summary_model).run(ctx),
        ]

    for model in (classifier_model, summary_model):
        for call in model.calls:
            _assert_clean("\n".join(str(m.content) for m in call))
    # Maskeli metin LLM'e gider; sıradan bilgi (tekne adı) korunur.
    assert "Rüzgar" in classifier_model.last_user
    _assert_clean(json.dumps(logs, ensure_ascii=False, default=str))
    # `agent_runs` satırına dönüşen kayıtlar
    _assert_clean(json.dumps([r.model_dump(exclude={"output"}) for r in results], default=str))
    assert all(r.status == "ok" for r in results)


async def test_failure_records_and_logs_do_not_contain_raw_text() -> None:
    model = ScriptedChatModel(responses=[RuntimeError("sağlayıcı kapalı")])
    ctx = AnalysisContext(call_id=uuid4(), segments=_segments())

    with capture_logs() as logs:
        result: Any = await CallClassifierAgent(model=model).run(ctx)

    assert result.status == "failed"
    _assert_clean(json.dumps(logs, ensure_ascii=False, default=str))
    _assert_clean(json.dumps(result.model_dump(), ensure_ascii=False, default=str))


def test_summary_with_personal_data_is_rejected() -> None:
    """Özetleyici çıktısında kişisel veri kalıbı bulunursa agent çıktıyı reddeder."""
    assert find_personal_data("Müşteriyi 0532 123 45 67 numarasından arayın") != []

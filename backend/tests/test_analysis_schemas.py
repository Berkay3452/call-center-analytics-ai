"""Çağrı analizi şemaları ve enum listeleri testleri."""

import json
from datetime import date
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.names import CALL_CLASSIFIER, CRM_EXTRACTION, SALES_ANALYZER, SUMMARIZER
from app.domain import enums
from app.schemas.analysis import (
    AnalysisResult,
    CallClassification,
    CallSummary,
    CrmExtraction,
    KpiSummary,
    SalesAnalysis,
)

EXAMPLE = Path(__file__).parents[2] / "docs" / "ornekler" / "analiz_sonucu_tuzla_marina.json"


# --- Enum listeleri -----------------------------------------------------------------------


def _all_enums() -> list[type[StrEnum]]:
    return [
        obj
        for obj in vars(enums).values()
        if isinstance(obj, type) and issubclass(obj, StrEnum) and obj is not StrEnum
    ]


def test_enum_values_are_lowercase_ascii_without_spaces() -> None:
    for enum_cls in _all_enums():
        for member in enum_cls:
            assert member.value == member.value.lower(), member
            assert member.value.isascii(), member
            assert " " not in member.value, member


def test_every_enum_member_has_turkish_label() -> None:
    missing = [m for e in _all_enums() for m in e if m not in enums.LABELS_TR]
    assert missing == []


# --- Hocanın örnek senaryosu ----------------------------------------------------------------


def test_example_json_matches_schema() -> None:
    result = AnalysisResult.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))

    assert result.status == "tamam"
    assert result.crm is not None
    assert result.crm.location == "Tuzla Marina"
    assert result.crm.service_mode == enums.ServiceMode.YERINDE_SERVIS
    assert result.crm.urgency == enums.Urgency.YUKSEK
    assert result.crm.next_action == enums.NextAction.SERVIS_RANDEVUSU_OLUSTUR


# --- Çağrı Sınıflandırma ----------------------------------------------------------------------


def test_classification_rejects_unknown_type_and_bad_confidence() -> None:
    with pytest.raises(ValidationError):
        CallClassification(call_type="bilinmeyen", confidence=0.5, reason="x")
    with pytest.raises(ValidationError):
        CallClassification(call_type=enums.CallType.SERVIS, confidence=1.2, reason="x")


# --- CRM Bilgi Çıkarım ------------------------------------------------------------------------


def test_crm_fields_default_to_none_not_invented() -> None:
    crm = CrmExtraction()

    assert crm.model_dump(exclude={"evidence"}) == dict.fromkeys(
        (
            "request_category",
            "location",
            "problem",
            "service_mode",
            "urgency",
            "potential_job",
            "next_action",
        )
    )


def test_crm_evidence_keys_must_be_field_names() -> None:
    CrmExtraction(location="Tuzla Marina", evidence={"location": "Tuzla Marina'da"})
    with pytest.raises(ValidationError, match="evidence"):
        CrmExtraction(evidence={"uydurma_alan": "x"})


# --- Satış Analiz: loss_reason kuralı --------------------------------------------------------


def test_loss_reason_required_when_lost() -> None:
    with pytest.raises(ValidationError, match="loss_reason zorunludur"):
        SalesAnalysis(outcome=enums.SalesOutcomeType.KAYBEDILDI, confidence=0.8)

    ok = SalesAnalysis(
        outcome=enums.SalesOutcomeType.KAYBEDILDI,
        loss_reason=enums.LossReason.FIYAT,
        confidence=0.8,
    )
    assert ok.loss_reason == enums.LossReason.FIYAT


@pytest.mark.parametrize(
    "outcome", [enums.SalesOutcomeType.SATISA_DONUSTU, enums.SalesOutcomeType.BEKLEMEDE]
)
def test_loss_reason_forbidden_when_not_lost(outcome: enums.SalesOutcomeType) -> None:
    with pytest.raises(ValidationError, match="yalnızca"):
        SalesAnalysis(outcome=outcome, loss_reason=enums.LossReason.FIYAT, confidence=0.8)

    assert SalesAnalysis(outcome=outcome, confidence=0.8).loss_reason is None


# --- Özetleme ---------------------------------------------------------------------------------


def test_summary_limits_sentences_and_key_points() -> None:
    CallSummary(summary="Bir. İki. Üç.")
    CallSummary(summary="Motor devir almıyor. Usta isteniyor.", key_points=["a", "b", "c"])
    with pytest.raises(ValidationError, match="3 cümle"):
        CallSummary(summary="Bir. İki. Üç. Dört.")
    with pytest.raises(ValidationError):
        CallSummary(summary="Kısa.", key_points=["a", "b", "c", "d"])


# --- Birleşik sonuç ---------------------------------------------------------------------------


def test_analysis_result_from_partial_outputs() -> None:
    call_id = uuid4()

    result = AnalysisResult.from_outputs(
        call_id=call_id,
        status="kismi",
        outputs={
            CALL_CLASSIFIER: {"call_type": "servis", "confidence": 0.9, "reason": "usta istiyor"},
            SUMMARIZER: {"summary": "Kısa özet.", "key_points": []},
        },
        errors={CRM_EXTRACTION: "bozuldu", SALES_ANALYZER: "bozuldu"},
        runs=[],
    )

    assert result.status == "kismi"
    assert result.classification is not None
    assert result.summary is not None
    assert result.crm is None
    assert result.sales is None
    assert set(result.errors) == {CRM_EXTRACTION, SALES_ANALYZER}


def test_analysis_status_values_are_fixed() -> None:
    with pytest.raises(ValidationError):
        AnalysisResult(call_id=uuid4(), status="bitti")


# --- KPI --------------------------------------------------------------------------------------


def _kpi(**overrides: object) -> KpiSummary:
    base: dict[str, object] = {
        "period_start": date(2026, 10, 1),
        "period_end": date(2026, 10, 31),
        "total_calls": 30,
        "new_customers": 5,
        "service_requests": 14,
        "quote_requests": 6,
        "urgent_requests": 3,
        "converted_sales": 9,
        "lost_by_reason": {enums.LossReason.FIYAT: 4, enums.LossReason.GEC_DONUS: 2},
        "top_problems": [{"name": "Motor arızası", "count": 7}],
        "busiest_marinas": [{"name": "Tuzla Marina", "count": 11}],
        "avg_answer_delay_s": 14.5,
    }
    base.update(overrides)
    return KpiSummary.model_validate(base)


def test_kpi_summary_valid_and_period_ordered() -> None:
    assert _kpi().lost_by_reason[enums.LossReason.FIYAT] == 4
    with pytest.raises(ValidationError, match="period_end"):
        _kpi(period_end=date(2026, 9, 1))
    with pytest.raises(ValidationError):
        _kpi(total_calls=-1)

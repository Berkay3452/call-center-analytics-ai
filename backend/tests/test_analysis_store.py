"""Analiz kayıt dönüşümleri (#47): sonuç → tablo satırları → API şeması. Veritabanı gerektirmez."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.agents.names import CRM_EXTRACTION
from app.db.models.ai import AgentRun as AgentRunRow
from app.db.models.ai import AnalysisResult as AnalysisRow
from app.domain.enums import LossReason, SalesOutcomeType
from app.schemas.analysis import AgentRun, AnalysisResult, CrmExtraction
from app.services.analysis_store import analysis_from_rows, analysis_row_values, run_row_values

EXAMPLE = Path(__file__).parents[2] / "docs" / "ornekler" / "analiz_sonucu_tuzla_marina.json"


def full_result() -> AnalysisResult:
    result = AnalysisResult.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    runs = [
        AgentRun(agent=a, status="ok", attempts=1, latency_ms=1200, model="m", prompt_version="v1")
        for a in ("call_classifier", "crm_extraction", "sales_analyzer", "summarizer")
    ]
    return result.model_copy(update={"runs": runs})


def to_row(result: AnalysisResult, version: int = 1) -> AnalysisRow:
    row = AnalysisRow(version=version, **analysis_row_values(result))
    row.created_at = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    return row


def to_run_rows(result: AnalysisResult) -> list[AgentRunRow]:
    return [AgentRunRow(**run_row_values(r, uuid4())) for r in result.runs]


def test_full_result_round_trips_through_rows() -> None:
    result = full_result()

    out = analysis_from_rows(to_row(result), to_run_rows(result))

    assert out.version == 1
    assert out.status == "tamam"
    assert out.classification == result.classification
    assert out.crm == result.crm
    assert out.sales == result.sales
    assert out.summary == result.summary
    assert [r.agent for r in out.runs] == [r.agent for r in result.runs]


def test_row_values_use_plain_enum_strings() -> None:
    values = analysis_row_values(full_result())

    assert values["call_type"] == "servis"
    assert values["request_category"] == "makine"
    assert values["next_action"] == "servis_randevusu_olustur"
    assert values["sales_outcome"] == "beklemede"
    assert values["loss_reason"] is None
    assert values["crm_evidence"]["location"] == "Tuzla Marina'da teknem var"
    assert type(values["call_type"]) is str


def test_failed_agent_leaves_its_columns_unset() -> None:
    result = full_result().model_copy(
        update={"crm": None, "status": "kismi", "errors": {CRM_EXTRACTION: "doğrulama hatası"}}
    )
    values = analysis_row_values(result)

    assert "request_category" not in values
    assert "crm_evidence" not in values
    out = analysis_from_rows(to_row(result), to_run_rows(result))
    assert out.crm is None  # agent başarısız: CRM alanı yok
    assert out.errors == {CRM_EXTRACTION: "doğrulama hatası"}
    assert out.classification is not None


def test_crm_found_nothing_is_not_confused_with_crm_failed() -> None:
    result = full_result().model_copy(update={"crm": CrmExtraction()})

    out = analysis_from_rows(to_row(result), to_run_rows(result))

    assert out.crm == CrmExtraction()  # çalıştı ama konuşmada bilgi yoktu


def test_lost_sale_keeps_loss_reason() -> None:
    result = full_result()
    assert result.sales is not None
    lost = result.sales.model_copy(
        update={"outcome": SalesOutcomeType.KAYBEDILDI, "loss_reason": LossReason.FIYAT}
    )
    row = to_row(result.model_copy(update={"sales": lost}), version=2)

    out = analysis_from_rows(row, [])

    assert out.version == 2
    assert out.sales is not None
    assert out.sales.loss_reason == "fiyat"


def test_all_failed_result_has_no_agent_outputs() -> None:
    result = AnalysisResult(
        call_id=uuid4(),
        status="basarisiz",
        errors={a: "hata" for a in ("call_classifier", "crm_extraction", "sales_analyzer")},
    )

    out = analysis_from_rows(to_row(result), [])

    assert out.status == "basarisiz"
    assert out.classification is None
    assert out.sales is None
    assert out.summary is None
    assert out.crm is None

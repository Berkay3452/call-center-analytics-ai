"""API sözleşmesinin (#46) backend, frontend tipleri ve örnekler arasında aynı kalmasını denetler.

Bir alan yalnızca bir yerde eklenir/silinirse bu test kırılır. Ayrıntı: docs/api.md.
"""

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.domain.enums import SwitchboardOutcome
from app.schemas import analysis, api, assistant, common
from app.schemas.common import Page

ROOT = Path(__file__).parents[2]
API_TYPES_TS = ROOT / "frontend" / "lib" / "api-types.ts"
EXAMPLES = ROOT / "docs" / "ornekler" / "api"
API_DOC = ROOT / "docs" / "api.md"

# Frontend'de aynı adla interface'i olan backend modelleri.
SHARED_MODELS: list[type[BaseModel]] = [
    common.ErrorBody,
    common.ErrorResponse,
    analysis.CallClassification,
    analysis.CrmExtraction,
    analysis.SalesAnalysis,
    analysis.CallSummary,
    analysis.AgentRun,
    analysis.CountItem,
    analysis.DailyCount,
    analysis.KpiSummary,
    assistant.SourceRef,
    api.AnalysisOut,
    api.CallListItem,
    api.TranscriptSegmentOut,
    api.TranscriptOut,
    api.CallDetail,
    api.CrmRecordItem,
    api.SegmentIn,
    api.CallCreate,
    api.CallAccepted,
    api.CallStatus,
    api.ChatQuestion,
    api.ChatMessageOut,
    api.ChatReply,
    api.ChatSessionOut,
    api.ChatSessionDetail,
    api.StatusEvent,
    api.DeltaEvent,
    api.DoneEvent,
    api.ErrorEvent,
]

# Örnek dosya → doğrulandığı model.
EXAMPLE_MODELS: dict[str, Any] = {
    "cagri_listesi.json": Page[api.CallListItem],
    "cagri_detayi.json": api.CallDetail,
    "crm_listesi.json": Page[api.CrmRecordItem],
    "kpi_ozeti.json": analysis.KpiSummary,
    "cagri_olustur_istek.json": api.CallCreate,
    "cagri_kabul.json": api.CallAccepted,
    "cagri_durumu.json": api.CallStatus,
    "sohbet_soru_istek.json": api.ChatQuestion,
    "sohbet_cevabi.json": api.ChatReply,
    "sohbet_oturumu.json": api.ChatSessionDetail,
}


def ts_source() -> str:
    return API_TYPES_TS.read_text(encoding="utf-8")


def ts_interface_fields(name: str) -> set[str]:
    match = re.search(rf"export interface {name}(?:<[^>]+>)? \{{(.*?)\n\}}", ts_source(), re.S)
    assert match, f"frontend/lib/api-types.ts içinde '{name}' interface'i yok"
    return set(re.findall(r"^\s+([a-z_]+)\??:", match.group(1), re.M))


def ts_union(name: str) -> set[str]:
    match = re.search(rf"export type {name} =([^;]+);", ts_source())
    assert match, f"frontend/lib/api-types.ts içinde '{name}' tipi yok"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


@pytest.mark.parametrize("model", SHARED_MODELS, ids=lambda m: m.__name__)
def test_frontend_interfaces_match_backend_models(model: type[BaseModel]) -> None:
    assert ts_interface_fields(model.__name__) == set(model.model_fields)


def test_page_fields_match() -> None:
    assert ts_interface_fields("Page") == set(Page.model_fields)


@pytest.mark.parametrize(
    ("ts_name", "values"),
    [
        ("CallState", set(get_args(api.CallState))),
        ("Speaker", set(get_args(api.Speaker))),
        ("SourceKind", set(get_args(assistant.SourceKind))),
        ("StreamStage", set(get_args(api.StreamStage))),
        ("QuestionType", {m.value for m in assistant.QuestionType}),
        ("SwitchboardOutcome", {m.value for m in SwitchboardOutcome}),
    ],
)
def test_frontend_unions_match_backend(ts_name: str, values: set[str]) -> None:
    assert ts_union(ts_name) == values


@pytest.mark.parametrize("filename", sorted(EXAMPLE_MODELS))
def test_examples_validate(filename: str) -> None:
    data = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
    EXAMPLE_MODELS[filename].model_validate(data)


def test_every_example_is_checked() -> None:
    assert {p.name for p in EXAMPLES.glob("*.json")} == set(EXAMPLE_MODELS)


def test_stream_example_is_valid_sse() -> None:
    raw = (EXAMPLES / "sohbet_akisi.sse").read_text(encoding="utf-8")
    events = [block for block in raw.split("\n\n") if block.strip()]
    types: list[str] = []
    text = ""
    for block in events:
        name, data = block.splitlines()
        parsed = api.chat_stream_event_adapter.validate_json(data.removeprefix("data: "))
        assert name == f"event: {parsed.type}"
        types.append(parsed.type)
        if isinstance(parsed, api.DeltaEvent):
            text += parsed.text
        if isinstance(parsed, api.DoneEvent):
            assert parsed.reply.answer.content == text  # parçalar birleşince tam cevap
    assert types[0] == "status"
    assert types[-1] == "done"
    assert types.count("done") == 1


def test_every_shared_model_is_documented() -> None:
    doc = API_DOC.read_text(encoding="utf-8")
    models: list[type[BaseModel]] = [*SHARED_MODELS, api.CallFilters, api.PeriodFilter]
    for model in models:
        if model.__module__.endswith(("api", "analysis")):
            assert f"`{model.__name__}`" in doc, model.__name__


# --- Sözleşme kuralları -------------------------------------------------------------------


def test_call_create_needs_text() -> None:
    with pytest.raises(ValidationError, match="transcript veya segments"):
        api.CallCreate(started_at="2026-10-12T09:00:00Z", transcript="  ")
    api.CallCreate(started_at="2026-10-12T09:00:00Z", transcript="Müşteri: Merhaba")


@pytest.mark.parametrize("model", [api.CallFilters, api.PeriodFilter])
def test_filters_reject_reversed_dates(model: type[BaseModel]) -> None:
    with pytest.raises(ValidationError, match="date_to"):
        model.model_validate({"date_from": "2026-10-10", "date_to": "2026-10-01"})


def test_call_filters_limit_page_size() -> None:
    with pytest.raises(ValidationError):
        api.CallFilters(page_size=500)


def test_chat_question_has_no_owner_id() -> None:
    # Kimlik yalnızca X-User-Id başlığından gelir; gövdeden gelen kimliğe güvenilmez.
    assert "owner_id" not in api.ChatQuestion.model_fields


def test_call_state_includes_analysis_statuses() -> None:
    assert set(get_args(analysis.AnalysisStatus)) <= set(get_args(api.CallState))


def test_enum_dict_keys_are_enums() -> None:
    kpi = analysis.KpiSummary.model_validate(
        json.loads((EXAMPLES / "kpi_ozeti.json").read_text(encoding="utf-8"))
    )
    assert all(isinstance(k, StrEnum) for k in kpi.by_category)

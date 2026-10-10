"""Değerlendirme script'inin (scripts/evaluate.py) LLM'siz testleri."""

from itertools import pairwise
from uuid import uuid4

import pytest

from app.schemas.analysis import AnalysisResult
from scripts.evaluate import DATA, compare, load_context, load_truth

CALL_IDS = sorted(p.stem for p in (DATA / "calls").glob("call_*.json"))


@pytest.mark.parametrize("cid", CALL_IDS)
def test_every_synthetic_call_loads_as_context(cid: str) -> None:
    ctx = load_context(cid)

    assert len(ctx.segments) >= 15
    assert [s.idx for s in ctx.segments] == list(range(len(ctx.segments)))
    assert all(a.end_ms <= b.start_ms for a, b in pairwise(ctx.segments))
    assert ctx.call_info is not None and ctx.call_info.answer_delay_s is not None
    assert load_context(cid).call_id == ctx.call_id  # tekrar çalıştırmada aynı kimlik


def _result_from_truth(cid: str) -> AnalysisResult:
    truth = load_truth(cid)
    return AnalysisResult.model_validate(
        {
            "call_id": uuid4(),
            "status": "tamam",
            "classification": {"call_type": truth["call_type"], "confidence": 1, "reason": "x"},
            "crm": truth["crm"],
            "sales": {**truth["sales"], "confidence": 1},
            "summary": {"summary": "Özet.", "key_points": []},
        }
    )


@pytest.mark.parametrize("cid", CALL_IDS)
def test_truth_itself_scores_perfect(cid: str) -> None:
    scores = compare(load_truth(cid), _result_from_truth(cid))

    assert all(v is True for v in scores.values()), scores


def test_wrong_and_missing_fields_are_scored() -> None:
    result = _result_from_truth("call_001")
    assert result.crm is not None
    result.crm.urgency = None
    result.crm.location = "Kalamış Marina"
    result = result.model_copy(update={"sales": None})

    scores = compare(load_truth("call_001"), result)

    assert scores["urgency"] is False
    assert scores["location"] is False
    assert scores["sales_outcome"] is None  # agent başarısız: ölçülemedi
    assert scores["call_type"] is True

"""Duygu analizi ölçümü: etiket dosyası ve rapor betiği (#334). LLM çağrılmaz."""

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.domain.enums import Sentiment
from scripts import duygu_olcum

DATA = Path(__file__).parents[2] / "data" / "synthetic"
LABELS = duygu_olcum.load_labels()


def test_every_label_has_a_call_file_and_valid_values() -> None:
    assert len(LABELS) == 119
    for call_id, label in LABELS.items():
        folder = "duygu_ek" if call_id.startswith("duygu_ek") else "calls"
        assert (DATA / folder / f"{call_id}.json").exists(), call_id
        assert label["sentiment"] in {s.value for s in Sentiment}, call_id
        assert label["kume"] == ("duygu_ek" if folder == "duygu_ek" else "ana"), call_id
        # Şema kuralı etiketlerde de geçerli: şikâyet varsa duygu olumsuz.
        assert not label["complaint"] or label["sentiment"] == "olumsuz", call_id


def test_label_set_covers_all_classes_and_complaints() -> None:
    classes = {label["sentiment"] for label in LABELS.values()}
    assert classes == {"olumlu", "notr", "olumsuz"}
    assert sum(1 for label in LABELS.values() if label["complaint"]) >= 10
    assert sum(1 for label in LABELS.values() if label["zor"]) >= 10


def test_extra_calls_are_masked_and_well_formed() -> None:
    for path in sorted((DATA / "duygu_ek").glob("duygu_ek_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["call_id"] == path.stem
        assert {t["speaker"] for t in doc["turns"]} <= {"rep", "customer"}
        assert any(t["speaker"] == "customer" for t in doc["turns"])
        text = " ".join(t["text"] for t in doc["turns"])
        assert "@" not in text
        assert not re.search(r"\d{6,}", text)  # telefon/kimlik benzeri uzun sayı yok


def test_load_context_builds_ordered_segments() -> None:
    ctx = duygu_olcum.load_context("duygu_ek_08")
    assert ctx.segments[0].speaker == "rep"
    starts = [s.start_ms for s in ctx.segments]
    assert starts == sorted(starts)


def _row(call_id: str, truth: str, pred: str, complaint: bool = False) -> dict[str, Any]:
    label = dict(LABELS[call_id]) | {"sentiment": truth}
    return {
        "call_id": call_id,
        "truth": label,
        "status": "ok",
        "error": None,
        "attempts": 1,
        "latency_ms": 1000,
        "tokens": 100,
        "pred": {
            "sentiment": pred,
            "complaint": complaint,
            "reason": "Gerekçe.",
            "evidence": None,
            "confidence": 0.9,
        },
    }


def test_report_counts_confusion_and_complaints() -> None:
    rows = [
        _row("call_001", "notr", "notr"),
        _row("call_002", "notr", "olumsuz", complaint=True),
        _row("call_076", "olumlu", "olumlu"),
    ]
    rows[1]["truth"]["complaint"] = False
    text = duygu_olcum.report(rows, Settings())

    assert "%67 (2/3)" in text
    assert "yanlış pozitif 1" in text
    assert "| notr | 0 | 1 | 1 |" in text
    assert "call_002" in text  # yanlış etiketlenenler listesinde

"""Sentetik çağrı verisinin (data/synthetic) biçimini ve tutarlılığını denetler."""

import json
import re
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from app.agents.base import CallInfo
from app.agents.grounding import normalize
from app.domain.enums import CallType
from app.schemas.analysis import CrmExtraction, SalesAnalysis

DATA = Path(__file__).parents[2] / "data" / "synthetic"
CALL_IDS = sorted(p.stem for p in (DATA / "calls").glob("call_*.json"))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def calls() -> dict[str, dict[str, Any]]:
    return {cid: load(DATA / "calls" / f"{cid}.json") for cid in CALL_IDS}


def truths() -> dict[str, dict[str, Any]]:
    return {cid: load(DATA / "truth" / f"{cid}.truth.json") for cid in CALL_IDS}


def test_ten_calls_with_matching_files() -> None:
    assert len(CALL_IDS) == 10
    assert (
        sorted(p.name.removesuffix(".truth.json") for p in (DATA / "truth").glob("*.json"))
        == CALL_IDS
    )
    meta = load(DATA / "calls_meta.json")
    assert [m["call_id"] for m in meta] == CALL_IDS


@pytest.mark.parametrize("cid", CALL_IDS)
def test_dialogue_format(cid: str) -> None:
    doc = calls()[cid]

    assert doc["call_id"] == cid
    turns = doc["turns"]
    assert len(turns) >= 10
    assert {t["speaker"] for t in turns} == {"rep", "customer"}
    assert all(t["text"].strip() for t in turns)
    # Ardışık iki tur aynı konuşmacıya ait olmamalı (doğal diyalog akışı).
    assert all(a["speaker"] != b["speaker"] for a, b in pairwise(turns))


@pytest.mark.parametrize("cid", CALL_IDS)
def test_transcript_has_no_unmasked_personal_data(cid: str) -> None:
    text = " ".join(t["text"] for t in calls()[cid]["turns"])

    assert "@" not in text
    assert not re.search(r"\d{6,}", text.replace(" ", "")), "uzun rakam dizisi (telefon/kimlik?)"


@pytest.mark.parametrize("cid", CALL_IDS)
def test_truth_matches_backend_schemas(cid: str) -> None:
    truth = truths()[cid]

    assert truth["call_id"] == cid
    CallType(truth["call_type"])
    crm = CrmExtraction.model_validate(truth["crm"])
    SalesAnalysis.model_validate({**truth["sales"], "confidence": 1.0})
    assert set(truth["crm"]) == set(CrmExtraction.model_fields) - {"evidence"}
    if crm.location:
        text = normalize(" ".join(t["text"] for t in calls()[cid]["turns"]))
        assert normalize(crm.location).split()[0] in text, "lokasyon konuşmada geçmiyor"


@pytest.mark.parametrize("cid", CALL_IDS)
def test_meta_is_valid_call_info(cid: str) -> None:
    meta = next(m for m in load(DATA / "calls_meta.json") if m["call_id"] == cid)

    info = CallInfo(
        started_at=meta["started_at"],
        answer_delay_s=meta["answer_delay_s"],
        duration_s=meta["duration_s"],
        outcome=meta["switchboard_outcome"],
    )
    assert info.answer_delay_s is not None and info.answer_delay_s >= 0
    assert set(meta["customer_ref"]) == {"customer", "boat", "boat_model", "marina"}


def test_distribution_covers_every_class() -> None:
    t = truths()

    assert Counter(x["call_type"] for x in t.values()) == {
        "acil": 2,
        "servis": 3,
        "teklif": 2,
        "yeni_musteri": 1,
        "bilgi": 2,
    }
    assert Counter(x["sales"]["outcome"] for x in t.values()) == {
        "satisa_donustu": 4,
        "kaybedildi": 4,
        "beklemede": 2,
    }
    lost = sorted(
        x["sales"]["loss_reason"] for x in t.values() if x["sales"]["outcome"] == "kaybedildi"
    )
    assert lost == ["fiyat", "gec_donus", "rakip", "takvim"]


def test_hoca_scenario_is_first_call() -> None:
    first = calls()["call_001"]["turns"][1]["text"]
    crm = truths()["call_001"]["crm"]

    assert "gaz verdiğimde devir yükselmiyor" in first
    assert crm["location"] == "Tuzla Marina"
    assert (crm["urgency"], crm["next_action"]) == ("yuksek", "servis_randevusu_olustur")


def test_customer_and_boat_pairs_are_unique() -> None:
    refs = [
        (m["customer_ref"]["customer"], m["customer_ref"]["boat"])
        for m in load(DATA / "calls_meta.json")
    ]

    assert len(set(refs)) == len(refs)

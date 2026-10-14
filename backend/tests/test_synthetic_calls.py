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


def test_thirty_calls_with_matching_files() -> None:
    assert len(CALL_IDS) == 30
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
    assert 15 <= len(turns) <= 30  # issue #12: 15–30 konuşma sırası
    assert {t["speaker"] for t in turns} == {"rep", "customer"}
    assert all(t["text"].strip() for t in turns)
    # Ardışık iki tur aynı konuşmacıya ait olmamalı (doğal diyalog akışı).
    assert all(a["speaker"] != b["speaker"] for a, b in pairwise(turns))


@pytest.mark.parametrize("cid", CALL_IDS)
def test_transcript_has_no_unmasked_personal_data(cid: str) -> None:
    text = " ".join(t["text"] for t in calls()[cid]["turns"])

    assert "@" not in text
    # Müşteri adları metinde açık geçmemeli; agent'lar yalnızca maskeli metni görür.
    names = {
        part
        for m in load(DATA / "calls_meta.json")
        for part in m["customer_ref"]["customer"].split()
    }
    leaked = {n for n in names if re.search(rf"{re.escape(n)}", text)}
    assert not leaked, f"maskesiz müşteri adı: {leaked}"
    assert "Selim" not in text, "maskesiz çalışan adı"
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
        "acil": 4,
        "servis": 11,
        "teklif": 6,
        "yeni_musteri": 4,
        "bilgi": 5,
    }
    assert Counter(x["sales"]["outcome"] for x in t.values()) == {
        "satisa_donustu": 10,
        "kaybedildi": 11,
        "beklemede": 9,
    }
    lost = Counter(
        x["sales"]["loss_reason"] for x in t.values() if x["sales"]["outcome"] == "kaybedildi"
    )
    # Altı kayıp nedeninin hepsi temsil ediliyor.
    assert lost == {"fiyat": 3, "gec_donus": 2, "rakip": 2, "takvim": 2, "guven": 1, "diger": 1}


def test_every_request_category_and_urgency_is_represented() -> None:
    t = truths()

    assert {x["crm"]["request_category"] for x in t.values()} == {
        None,
        "makine",
        "mekanik_hidrolik",
        "elektrik_elektronik",
        "su_sihhi_tesisat",
        "iklimlendirme",
        "tekne_guvenligi",
        "temizlik_bakim",
        "diger",
    }
    assert {x["crm"]["urgency"] for x in t.values()} == {"dusuk", "normal", "yuksek", "acil"}


def test_split_marks_untouchable_test_set() -> None:
    """Geliştirme çağrıları (001-010) prompt ayarında kullanılabilir; test çağrılarına bakılmaz."""
    split = {m["call_id"]: m["split"] for m in load(DATA / "calls_meta.json")}

    assert set(split.values()) == {"gelistirme", "test"}
    assert {c for c, v in split.items() if v == "gelistirme"} == set(CALL_IDS[:10])
    assert len([v for v in split.values() if v == "test"]) == 20


def test_hoca_scenario_is_first_call() -> None:
    first = calls()["call_001"]["turns"][1]["text"]
    crm = truths()["call_001"]["crm"]

    assert "gaz verdiğimde devir yükselmiyor" in first
    assert crm["location"] == "Tuzla Marina"
    assert (crm["urgency"], crm["next_action"]) == ("yuksek", "servis_randevusu_olustur")


def test_calls_have_unique_ids_and_start_times() -> None:
    """Aynı müşteri birden çok kez arayabilir; ama iki çağrı aynı anda başlamaz."""
    meta = load(DATA / "calls_meta.json")

    assert len({m["call_id"] for m in meta}) == len(meta)
    assert len({m["started_at"] for m in meta}) == len(meta)


def test_known_customers_use_their_own_boats() -> None:
    """customers_boats.json'da kayıtlı müşteri, kendi teknesiyle aranmalı (CRM eşleşmesi)."""
    known = {
        (c["full_name"], b["name"]): (b["model"], b["marina"])
        for c in load(DATA / "customers_boats.json")
        for b in c["boats"]
    }
    names = {name for name, _ in known}
    for m in load(DATA / "calls_meta.json"):
        ref = m["customer_ref"]
        if ref["customer"] in names:
            pair = (ref["customer"], ref["boat"])
            assert pair in known, f"{m['call_id']}: {pair} kayıtlı bir tekne değil"
            assert known[pair] == (ref["boat_model"], ref["marina"]), m["call_id"]

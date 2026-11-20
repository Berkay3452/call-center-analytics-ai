"""Embedding model karşılaştırma betiği (#336): soru seti bütünlüğü ve ölçüt hesapları."""

import json
from collections import Counter
from typing import Any

import pytest

from app.stt.metrics import normalize
from scripts.rag_model_karsilastirma import (
    comparison_table,
    evaluate,
    latency,
    load_notes,
    load_questions,
    rank_of,
    summarize,
)


def fold(text: str) -> str:
    """Aksansız karşılaştırma (yazım hatalı sorularda "Yildiz" ~ "Yıldız")."""
    return normalize(text).translate(str.maketrans("çğıöşü", "cgiosu"))


@pytest.fixture(scope="module")
def notes() -> list[dict[str, Any]]:
    return load_notes()


def test_hard_set_is_balanced_and_valid(notes: list[dict[str, Any]]) -> None:
    questions = load_questions("zor")
    assert len(questions) >= 40
    assert len({q["question"] for q in questions}) == len(questions)
    counts = Counter(q["kategori"] for q in questions)
    assert set(counts) == {"es_anlamli", "ekli", "kisa", "sayi", "yazim", "ayirt"}
    assert min(counts.values()) >= 6
    by_code = {n["code"]: n for n in notes}
    for q in questions:
        for code in q["expected_notes"]:
            note = by_code[code]
            assert note["owner_id"] == q["owner_id"]
            # `tum` kapsamında geçerli olması için soruda teknenin adı geçmeli.
            assert fold(note["boat_name"]) in fold(q["question"]), q["question"]


def test_all_set_combines_old_and_hard() -> None:
    old, hard = load_questions("eski"), load_questions("zor")
    assert len(old) == 14
    assert len(load_questions("hepsi")) == len(old) + len(hard)
    assert all(q["kategori"] == "eski" for q in old)


def test_unknown_expected_note_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    import scripts.rag_model_karsilastirma as mod

    data = tmp_path
    (data / "boat_notes.json").write_text(json.dumps(load_notes()), encoding="utf-8")
    (data / "rag_eval_zor.json").write_text(
        json.dumps([{"kategori": "x", "question": "q", "expected_notes": ["note_999"]}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "DATA", data)
    with pytest.raises(ValueError, match="Bilinmeyen not"):
        mod.load_questions("zor")


def test_summarize_metrics() -> None:
    result = summarize([1, 2, None, 4, 3])
    assert result["isabet@1"] == pytest.approx(0.2)
    assert result["isabet@3"] == pytest.approx(0.6)
    assert result["isabet@5"] == pytest.approx(0.8)
    assert result["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 4 + 1 / 3) / 5)


def test_scope_filters_other_owners(notes: list[dict[str, Any]]) -> None:
    sub = notes[:6]
    target = sub[0]
    other = next(n for n in sub if n["owner_id"] != target["owner_id"])
    vecs = [[1.0 if n is other else 0.0, 1.0 if n is target else 0.0] for n in sub]
    question = {"owner_id": target["owner_id"], "expected_notes": [target["code"]]}
    qvec = [1.0, 0.5]  # başka sahibin notuna daha yakın
    assert rank_of(qvec, vecs, sub, question, "sahip") == 1
    assert rank_of(qvec, vecs, sub, question, "tum") == 2


def test_reranker_reorders_only_the_top_candidates(notes: list[dict[str, Any]]) -> None:
    sub = notes[:4]
    target = sub[3]
    vecs = [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2], [0.7, 0.3]]  # vektör sırası: 0, 1, 2, 3
    question = {"question": "q", "owner_id": 0, "expected_notes": [target["code"]]}
    qvec = [1.0, 0.0]
    assert rank_of(qvec, vecs, sub, question, "tum") == 4

    def prefers_target(_query: str, passages: list[str]) -> list[float]:
        return [1.0 if p == target["content"] else 0.0 for p in passages]

    assert rank_of(qvec, vecs, sub, question, "tum", prefers_target) == 1
    # İlk N'in dışındaki notlar yeniden sıralanmaz: hedef 4. sıradaysa ve N=2 ise 4 kalır.
    import scripts.rag_model_karsilastirma as mod

    original = mod.RERANK_TOP
    try:
        mod.RERANK_TOP = 2
        assert rank_of(qvec, vecs, sub, question, "tum", prefers_target) == 4
    finally:
        mod.RERANK_TOP = original


def test_oracle_embedder_scores_perfectly(notes: list[dict[str, Any]]) -> None:
    questions = load_questions("hepsi")
    index = {n["content"]: i for i, n in enumerate(notes)}
    by_question = {q["question"]: index_of(notes, q["expected_notes"][0]) for q in questions}

    def one_hot(i: int) -> list[float]:
        vec = [0.0] * len(notes)
        vec[i] = 1.0
        return vec

    def passages(texts: list[str]) -> list[list[float]]:
        return [one_hot(index[t]) for t in texts]

    def queries(texts: list[str]) -> list[list[float]]:
        return [one_hot(by_question[t]) for t in texts]

    result = evaluate(queries, passages, questions, notes)
    assert result["dim"] == len(notes)
    for scope in ("sahip", "tum"):
        total = result[scope]["toplam"]
        assert total["isabet@1"] == 1.0 and total["mrr"] == 1.0
        assert len(result[scope]["siralar"]) == len(questions)
    lat = latency(queries, questions[:3])
    assert lat["ilk_ms"] >= 0 and lat["p95_ms"] >= lat["medyan_ms"] >= 0
    result.update(gecikme=lat, ad="oracle", bellek_mb=None)
    table = comparison_table([result])
    assert "oracle" in table and "1.00" in table and "Tüm notlar" in table


def index_of(notes: list[dict[str, Any]], code: str) -> int:
    return next(i for i, n in enumerate(notes) if n["code"] == code)

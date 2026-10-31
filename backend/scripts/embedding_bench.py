"""Embedding servisinin hızını ve arama isabetini ölçer (#179); veritabanına yazmaz.

Kullanım (backend/ klasöründe; ölçülecek TEI servisi çalışıyor olmalı):

    python -m scripts.embedding_bench --url http://localhost:8080                 # bge-m3
    python -m scripts.embedding_bench --url http://localhost:8081 \
        --query-prefix "query: " --passage-prefix "passage: "                      # e5

Sorular `data/synthetic/rag_eval.json`, notlar `boat_notes.json`. İsabet yalnızca vektör
benzerliğiyle (hibrit arama değil) ve sorunun sahibinin notları arasında hesaplanır; notlar bellekte
indekslenir. Süre: ilk istek, tek sorgu medyan/p95 (3 tur) ve 85 notun toplu gömülme süresi.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx

DATA = Path(__file__).parents[2] / "data" / "synthetic"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--query-prefix", default="")
    parser.add_argument("--passage-prefix", default="")
    args = parser.parse_args()

    questions = json.loads((DATA / "rag_eval.json").read_text(encoding="utf-8"))
    notes = json.loads((DATA / "boat_notes.json").read_text(encoding="utf-8"))
    code_to_id = {n["code"]: n["id"] for n in notes}

    with httpx.Client(timeout=120) as client:

        def embed(texts: list[str]) -> list[list[float]]:
            resp = client.post(f"{args.url}/embed", json={"inputs": texts, "normalize": True})
            resp.raise_for_status()
            vectors: list[list[float]] = resp.json()
            return vectors

        def timed_query(text: str) -> float:
            started = time.perf_counter()
            embed([args.query_prefix + text])
            return (time.perf_counter() - started) * 1000

        first_ms = timed_query(questions[0]["question"])
        times = sorted(timed_query(q["question"]) for _ in range(3) for q in questions)

        started = time.perf_counter()
        vectors: list[list[float]] = []
        for i in range(0, len(notes), 16):
            vectors += embed([args.passage_prefix + n["content"] for n in notes[i : i + 16]])
        index_s = time.perf_counter() - started

        ranks: list[int | None] = []
        for q in questions:
            qv = embed([args.query_prefix + q["question"]])[0]
            scored = sorted(
                (
                    (sum(a * b for a, b in zip(qv, vec, strict=True)), n["id"])
                    for n, vec in zip(notes, vectors, strict=True)
                    if n["owner_id"] == q["owner_id"]
                ),
                reverse=True,
            )
            ids = [note_id for _, note_id in scored]
            expected = {code_to_id[c] for c in q["expected_notes"]}
            ranks.append(next((k + 1 for k, i in enumerate(ids) if i in expected), None))

    n = len(ranks)
    hit1 = sum(1 for r in ranks if r == 1) / n
    hit3 = sum(1 for r in ranks if r is not None and r <= 3) / n
    mrr = sum(1 / r for r in ranks if r) / n
    print(
        f"ilk istek: {first_ms:.0f} ms | tek sorgu: medyan {statistics.median(times):.0f} ms, "
        f"p95 {times[int(0.95 * (len(times) - 1))]:.0f} ms, en uzun {times[-1]:.0f} ms"
    )
    print(f"{len(notes)} not toplu gömülme: {index_s:.1f} sn")
    print(f"isabet@1 {hit1:.2f} | isabet@3 {hit3:.2f} | MRR {mrr:.2f} | sıralar {ranks}")


if __name__ == "__main__":
    main()

"""Hibrit aramanın doğruluğunu ölçer (#26): örnek sorularda beklenen not ilk 3'te mi?

Kullanım (backend/ klasöründe; seed + `python -m scripts.rag_index` sonrası):

    python -m scripts.rag_eval                       # .env'deki embedding sağlayıcısı
    python -m scripts.rag_eval --mode vector         # kıyas: yalnızca vektör (veya text)
    python -m scripts.rag_eval --min-similarity 0.45 --out rag_sonuc.json

Sorular: `data/synthetic/rag_eval.json` (soru, tekne sahibi, beklenen usta notu kodları).
Ölçütler: isabet@1, isabet@3 (beklenen notlardan biri ilk 1 / 3 sonuçta mı) ve MRR.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.rag.embedders import build_embedder
from app.rag.search import hybrid_search

DATA = Path(__file__).parents[2] / "data" / "synthetic"


def load_questions() -> tuple[list[dict[str, Any]], dict[str, str]]:
    questions = json.loads((DATA / "rag_eval.json").read_text(encoding="utf-8"))
    notes = json.loads((DATA / "boat_notes.json").read_text(encoding="utf-8"))
    note_ids = {n["code"]: n["id"] for n in notes}
    return questions, note_ids


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    settings = Settings()
    embedder = build_embedder(settings, args.provider)
    questions, note_ids = load_questions()
    engine = create_engine(settings, null_pool=True)
    rows: list[dict[str, Any]] = []
    try:
        async with create_session_factory(engine)() as session:
            for q in questions:
                hits = await hybrid_search(
                    session,
                    embedder,
                    UUID(q["owner_id"]),
                    q["question"],
                    limit=args.k,
                    min_similarity=args.min_similarity,
                    mode=args.mode,
                )
                expected = {note_ids[c] for c in q["expected_notes"]}
                found = [h.source.record_id for h in hits]
                rank = next((i + 1 for i, rid in enumerate(found) if rid in expected), None)
                rows.append(
                    {
                        "question": q["question"],
                        "rank": rank,
                        "hits": [
                            {
                                "title": h.source.title,
                                "similarity": h.similarity,
                                "text_match": h.text_match,
                                "excerpt": h.text[:80],
                            }
                            for h in hits
                        ],
                    }
                )
                mark = f"{rank}." if rank else "YOK"
                print(f"  [{mark:>3}] {q['question']}")
    finally:
        await engine.dispose()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--provider", choices=["tei", "openai_compatible", "hash"])
    parser.add_argument("--mode", choices=["hybrid", "vector", "text"], default="hybrid")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--min-similarity", type=float, default=0.0)
    parser.add_argument("--out", help="Sonuçları JSON olarak kaydet")
    args = parser.parse_args()

    rows = asyncio.run(run(args))
    n = len(rows)
    at1 = sum(r["rank"] == 1 for r in rows) / n
    at_k = sum(r["rank"] is not None for r in rows) / n
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / n
    print(
        f"\n{args.mode}: isabet@1={at1:.2f}  isabet@{args.k}={at_k:.2f}  MRR={mrr:.2f}  ({n} soru)"
    )
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

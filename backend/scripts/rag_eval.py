"""Hibrit aramanın doğruluğunu ölçer (#26): örnek sorularda beklenen not ilk 3'te mi?

Kullanım (backend/ klasöründe; seed + `python -m scripts.rag_index` sonrası):

    python -m scripts.rag_eval                       # .env'deki embedding sağlayıcısı
    python -m scripts.rag_eval --mode vector         # kıyas: yalnızca vektör (veya text)
    python -m scripts.rag_eval --min-similarity 0.45 --out rag_sonuc.json
    python -m scripts.rag_eval --set hepsi --k 5 --rerank   # 62 soru, reranker ile (#357)

Sorular: `data/synthetic/rag_eval.json` (soru, tekne sahibi, beklenen usta notu kodları);
`--set zor|hepsi` ile #336'daki 48 zor soru da eklenir (`rag_eval_zor.json`).
`--rerank`: üretimdeki gibi RRF adaylarını reranker (`RERANKER_URL`) ile yeniden sıralar.
`--rerank-model <HF kimliği>`: aynı modeli TEI servisi olmadan yerel CrossEncoder ile çalıştırır
(yalnızca ölçüm; `uv run --with torch --with sentence-transformers` gerekir).
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
from app.rag.rerankers import Reranker, build_reranker
from app.rag.search import hybrid_search

DATA = Path(__file__).parents[2] / "data" / "synthetic"


class LocalReranker:
    """Ölçüm için: sentence-transformers CrossEncoder'ı `Reranker` arayüzüne uyarlar."""

    def __init__(self, model: str) -> None:
        from scripts.rag_model_karsilastirma import cross_encoder

        self.model_name = model
        self._score = cross_encoder(model)

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        return await asyncio.to_thread(self._score, query, texts)


def load_questions(which: str = "eski") -> tuple[list[dict[str, Any]], dict[str, str]]:
    if which == "eski":
        questions = json.loads((DATA / "rag_eval.json").read_text(encoding="utf-8"))
    else:
        from scripts.rag_model_karsilastirma import load_questions as load_set

        questions = load_set(which)
    notes = json.loads((DATA / "boat_notes.json").read_text(encoding="utf-8"))
    note_ids = {n["code"]: n["id"] for n in notes}
    return questions, note_ids


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    settings = Settings()
    embedder = build_embedder(settings, args.provider)
    questions, note_ids = load_questions(args.set)
    reranker: Reranker | None = None
    if args.rerank_model:
        reranker = LocalReranker(args.rerank_model)
    elif args.rerank:
        reranker = build_reranker(settings)
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
                    reranker=reranker,
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
    parser.add_argument("--set", choices=["eski", "zor", "hepsi"], default="eski")
    parser.add_argument("--rerank", action="store_true", help="RRF adaylarını reranker ile sırala")
    parser.add_argument("--rerank-model", help="Yerel CrossEncoder ile ölç (TEI servisi gerekmez)")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--min-similarity", type=float, default=0.0)
    parser.add_argument("--out", help="Sonuçları JSON olarak kaydet")
    args = parser.parse_args()

    rows = asyncio.run(run(args))
    n = len(rows)
    at1 = sum(r["rank"] == 1 for r in rows) / n
    at_k = sum(r["rank"] is not None for r in rows) / n
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / n
    label = args.mode + (" + reranker" if args.rerank or args.rerank_model else "")
    print(f"\n{label}: isabet@1={at1:.2f}  isabet@{args.k}={at_k:.2f}  MRR={mrr:.2f}  ({n} soru)")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

"""Embedding modellerini aynı soru setinde karşılaştırır (#336): isabet@k, MRR, gecikme, bellek.

Veritabanına ve üretim `rag_chunks` tablosuna **dokunmaz**: notlar bellekte gömülür, arama saf
vektör benzerliğidir (kosinüs). Yalnızca sentetik veri (`data/synthetic`). Her model ayrı süreçte
koşulursa tepe bellek doğru çıkar.

Kullanım (backend/ klasöründe):

    # Referans: çalışan TEI servisi (bge-m3)
    python -m scripts.rag_model_karsilastirma --backend tei --url http://localhost:8080 \\
        --name bge-m3 --out sonuc_bge-m3.json
    # Yerel sentence-transformers (torch geçici eklenir; önbellek D: diskine yönlendirilmeli)
    uv run --with torch --with sentence-transformers python -m scripts.rag_model_karsilastirma \\
        --backend st --model intfloat/multilingual-e5-large --query-prefix "query: " \\
        --passage-prefix "passage: " --name e5-large --out sonuc_e5.json
    # OpenAI uyumlu API (anahtar yalnız ortam değişkeninden; yalnız sentetik metin gider)
    python -m scripts.rag_model_karsilastirma --backend openai --base-url <url> --model <ad> \\
        --api-key-env EMBEDDING_API_KEY --name hf-bge-m3

    # Birden çok sonucu tek tabloda topla
    python -m scripts.rag_model_karsilastirma --compare sonuc_*.json

Soru kümesi (`--set`): `eski` (rag_eval.json, 14 soru), `zor` (rag_eval_zor.json: eş anlamlı, ekli
Türkçe, kısa sorgu, sayı/ölçü, yazım hatalı, benzer notları ayırma) ya da `hepsi` (varsayılan).
Kapsam: `sahip` (üretimdeki gibi yalnız sorunun sahibinin notları) ve `tum` (85 notun hepsi; daha
zor, tekne adı ayırt etmeli).
"""

import argparse
import json
import os
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

DATA = Path(__file__).parents[2] / "data" / "synthetic"
KS = (1, 3, 5)
SCOPES = ("sahip", "tum")
Embed = Callable[[list[str]], list[list[float]]]


def load_questions(which: str) -> list[dict[str, Any]]:
    """Soruları yükler; sahip (`owner_id`) beklenen notun sahibinden türetilir."""
    notes = {n["code"]: n for n in json.loads((DATA / "boat_notes.json").read_text("utf-8"))}
    parts: list[tuple[str, list[dict[str, Any]]]] = []
    if which in ("eski", "hepsi"):
        old = json.loads((DATA / "rag_eval.json").read_text("utf-8"))
        parts.append(("eski", [{**q, "kategori": "eski"} for q in old]))
    if which in ("zor", "hepsi"):
        parts.append(("zor", json.loads((DATA / "rag_eval_zor.json").read_text("utf-8"))))
    questions: list[dict[str, Any]] = []
    for _, items in parts:
        for q in items:
            missing = [c for c in q["expected_notes"] if c not in notes]
            if missing:
                raise ValueError(f"Bilinmeyen not: {missing} ({q['question']})")
            owner = notes[q["expected_notes"][0]]["owner_id"]
            questions.append({**q, "owner_id": q.get("owner_id", owner)})
    return questions


def load_notes() -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = json.loads((DATA / "boat_notes.json").read_text("utf-8"))
    return notes


def rank_of(
    qvec: list[float],
    note_vecs: list[list[float]],
    notes: list[dict[str, Any]],
    question: dict[str, Any],
    scope: str,
) -> int | None:
    """Beklenen notlardan birinin sırası (1 tabanlı) ya da None. Vektörler normalize varsayılır."""
    expected = {n["id"] for n in notes if n["code"] in question["expected_notes"]}
    scored = sorted(
        (
            (sum(a * b for a, b in zip(qvec, vec, strict=True)), n["id"])
            for n, vec in zip(notes, note_vecs, strict=True)
            if scope == "tum" or n["owner_id"] == question["owner_id"]
        ),
        reverse=True,
    )
    return next((i + 1 for i, (_, note_id) in enumerate(scored) if note_id in expected), None)


def summarize(ranks: list[int | None]) -> dict[str, float]:
    n = len(ranks)
    out = {f"isabet@{k}": sum(r is not None and r <= k for r in ranks) / n for k in KS}
    out["mrr"] = sum(1 / r for r in ranks if r) / n
    out["n"] = float(n)
    return out


def evaluate(
    embed_queries: Embed,
    embed_passages: Embed,
    questions: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Tüm kapsamlar ve kategoriler için ölçütleri hesaplar (gecikme ayrıca ölçülür)."""
    started = time.perf_counter()
    note_vecs: list[list[float]] = []
    for i in range(0, len(notes), 16):
        note_vecs += embed_passages([n["content"] for n in notes[i : i + 16]])
    index_s = time.perf_counter() - started
    qvecs = [embed_queries([q["question"]])[0] for q in questions]
    result: dict[str, Any] = {"index_s": round(index_s, 2), "dim": len(note_vecs[0])}
    for scope in SCOPES:
        ranks = [
            rank_of(qv, note_vecs, notes, q, scope) for qv, q in zip(qvecs, questions, strict=True)
        ]
        by_cat: dict[str, dict[str, float]] = {}
        for cat in dict.fromkeys(q["kategori"] for q in questions):
            by_cat[cat] = summarize(
                [r for r, q in zip(ranks, questions, strict=True) if q["kategori"] == cat]
            )
        result[scope] = {
            "toplam": summarize(ranks),
            "kategori": by_cat,
            "siralar": ranks,
        }
    return result


def latency(embed_queries: Embed, questions: list[dict[str, Any]]) -> dict[str, float]:
    """İlk istek ve tek sorgu gecikmesi (ms): 3 tur, medyan ve p95."""

    def one(text: str) -> float:
        started = time.perf_counter()
        embed_queries([text])
        return (time.perf_counter() - started) * 1000

    first = one(questions[0]["question"])
    times = sorted(one(q["question"]) for _ in range(3) for q in questions)
    return {
        "ilk_ms": round(first, 1),
        "medyan_ms": round(statistics.median(times), 1),
        "p95_ms": round(times[int(0.95 * (len(times) - 1))], 1),
    }


# --- Arka uçlar -------------------------------------------------------------------------------


def tei_embed(url: str) -> Callable[[list[str]], list[list[float]]]:
    client = httpx.Client(timeout=300)

    def embed(texts: list[str]) -> list[list[float]]:
        resp = client.post(f"{url.rstrip('/')}/embed", json={"inputs": texts, "normalize": True})
        resp.raise_for_status()
        vectors: list[list[float]] = resp.json()
        return vectors

    return embed


def openai_embed(
    base_url: str, model: str, api_key: str
) -> Callable[[list[str]], list[list[float]]]:
    client = httpx.Client(timeout=300, headers={"Authorization": f"Bearer {api_key}"})

    def embed(texts: list[str]) -> list[list[float]]:
        for attempt in range(6):
            resp = client.post(
                f"{base_url.rstrip('/')}/embeddings", json={"model": model, "input": texts}
            )
            if resp.status_code == 429:  # kota: bekle ve yeniden dene
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [_normalize(d["embedding"]) for d in data]
        raise RuntimeError("Embedding API kotası doldu (429), yeniden denemeler tükendi.")

    return embed


def st_embed(model: str, trust_remote_code: bool) -> Callable[[list[str]], list[list[float]]]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit(
            "sentence-transformers yok: uv run --with torch --with sentence-transformers python ..."
        )
    encoder = SentenceTransformer(model, device="cpu", trust_remote_code=trust_remote_code)

    def embed(texts: list[str]) -> list[list[float]]:
        vectors = encoder.encode(texts, normalize_embeddings=True, batch_size=16)
        return [[float(x) for x in v] for v in vectors]

    return embed


def _normalize(vec: list[float]) -> list[float]:
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def container_memory(name: str) -> str | None:
    """TEI konteynerinin bellek kullanımı (docker stats); ölçülemezse None."""
    import subprocess

    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


# --- Çıktı ------------------------------------------------------------------------------------


def comparison_table(results: list[dict[str, Any]]) -> str:
    lines = []
    for scope, title in (("sahip", "Sahip kapsamı (üretimdeki gibi)"), ("tum", "Tüm notlar (zor)")):
        lines += [
            f"**{title}**",
            "",
            "| Model | isabet@1 | isabet@3 | isabet@5 | MRR | Sorgu medyan | Sorgu p95 | "
            "İndeksleme | Bellek |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            t = r[scope]["toplam"]
            lat = r["gecikme"]
            mem = r.get("bellek_mb")
            mem_text = f"{mem:.0f} MB" if mem else (r.get("konteyner_bellek") or "—")
            lines.append(
                f"| {r['ad']} | {t['isabet@1']:.2f} | {t['isabet@3']:.2f} | {t['isabet@5']:.2f} | "
                f"{t['mrr']:.2f} | {lat['medyan_ms']:.0f} ms | {lat['p95_ms']:.0f} ms | "
                f"{r['index_s']:.1f} sn | {mem_text} |"
            )
        lines.append("")
    cats = list(results[0]["tum"]["kategori"])
    lines += [
        "**Kategori başına isabet@3 (tüm notlar)**",
        "",
        "| Model | " + " | ".join(cats) + " |",
    ]
    lines.append("|---|" + "---|" * len(cats))
    for r in results:
        cells = [f"{r['tum']['kategori'][c]['isabet@3']:.2f}" for c in cats]
        lines.append(f"| {r['ad']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--backend", choices=["tei", "openai", "st"])
    parser.add_argument("--name", help="Tabloda görünecek model adı")
    parser.add_argument("--url", default="http://localhost:8080", help="TEI adresi")
    parser.add_argument("--base-url", help="OpenAI uyumlu API adresi (.../v1)")
    parser.add_argument("--model", help="openai: model adı; st: Hugging Face model kimliği")
    parser.add_argument("--api-key-env", default="EMBEDDING_API_KEY")
    parser.add_argument("--query-prefix", default="")
    parser.add_argument("--passage-prefix", default="")
    parser.add_argument(
        "--trust-remote-code", action="store_true", help="st: model kodunu çalıştır"
    )
    parser.add_argument("--set", dest="qset", choices=["eski", "zor", "hepsi"], default="hepsi")
    parser.add_argument("--tei-container", help="TEI konteyner adı (bellek için docker stats)")
    parser.add_argument("--out", help="Sonucu JSON olarak kaydet")
    parser.add_argument("--compare", nargs="+", help="Kayıtlı sonuç JSON'larını tabloya topla")
    args = parser.parse_args()

    if args.compare:
        results = [json.loads(Path(p).read_text("utf-8")) for p in args.compare]
        print(comparison_table(results))
        return
    if not args.backend:
        parser.error("--backend ya da --compare gerekli")

    if args.backend == "tei":
        raw = tei_embed(args.url)
    elif args.backend == "openai":
        key = os.environ.get(args.api_key_env)
        if not (args.base_url and args.model and key):
            parser.error(
                f"openai: --base-url, --model ve {args.api_key_env} ortam değişkeni gerekli"
            )
        raw = openai_embed(args.base_url, args.model, key)
    else:
        if not args.model:
            parser.error("st: --model gerekli")
        raw = st_embed(args.model, args.trust_remote_code)

    def embed_queries(texts: list[str]) -> list[list[float]]:
        return raw([args.query_prefix + t for t in texts])

    def embed_passages(texts: list[str]) -> list[list[float]]:
        return raw([args.passage_prefix + t for t in texts])

    questions = load_questions(args.qset)
    notes = load_notes()
    name = args.name or args.model or args.backend
    print(f"{name}: {len(questions)} soru, {len(notes)} not", flush=True)
    result = evaluate(embed_queries, embed_passages, questions, notes)
    result["gecikme"] = latency(embed_queries, questions)
    result["ad"] = name
    result["set"] = args.qset
    result["sorular"] = len(questions)
    from scripts.stt_benchmark import peak_memory_mb

    result["bellek_mb"] = peak_memory_mb() if args.backend == "st" else None
    if args.tei_container:
        result["konteyner_bellek"] = container_memory(args.tei_container)
    if result["dim"] != 1024:
        print(f"UYARI: boyut {result['dim']} (rag_chunks sütunu 1024; yeniden indeks gerekir)")
    print(comparison_table([result]))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        print(f"\nSonuç: {args.out}")


if __name__ == "__main__":
    main()

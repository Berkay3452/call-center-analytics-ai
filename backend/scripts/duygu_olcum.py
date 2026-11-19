"""Duygu Analiz Agent'ını sentetik çağrılarda gerçek LLM ile ölçer (#334).

Kullanım (backend/ klasöründe, .env'de LLM ayarları dolu olmalı):

    python -m scripts.duygu_olcum                       # 100 ana çağrı + 19 ek çağrı
    python -m scripts.duygu_olcum --calls call_004,duygu_ek_08
    python -m scripts.duygu_olcum --sure 12             # 4 agent ile 5 agent süre karşılaştırması
    python -m scripts.duygu_olcum --out sonuc.json      # ham sonuçları da kaydet
    python -m scripts.duygu_olcum --rapor sonuc.json    # kayıtlı sonuçtan rapor (LLM çağrılmaz)

Etiketler `data/synthetic/duygu_etiketleri.json` dosyasındadır (elle, model çıktısı görülmeden
verildi). Yalnızca sentetik ve maskeli metin kullanılır; gerçek müşteri verisi yoktur.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.agents.base import AnalysisContext, Segment
from app.agents.names import SENTIMENT_ANALYZER
from app.agents.orchestrator import Orchestrator
from app.agents.registry import default_stages
from app.agents.sentiment_analyzer import SentimentAnalyzerAgent
from app.core.config import Settings
from app.domain.enums import Sentiment

DATA = Path(__file__).parents[2] / "data" / "synthetic"
CLASSES = [s.value for s in Sentiment]


def load_labels() -> dict[str, dict[str, Any]]:
    doc = json.loads((DATA / "duygu_etiketleri.json").read_text(encoding="utf-8"))
    labels: dict[str, dict[str, Any]] = doc["calls"]
    return labels


def load_splits() -> dict[str, str]:
    """Çağrı → küme (gelistirme | test). Test kümesi istem ayarında kullanılmaz."""
    meta = json.loads((DATA / "calls_meta.json").read_text(encoding="utf-8"))
    return {m["call_id"]: m["split"] for m in meta}


def load_context(call_id: str) -> AnalysisContext:
    folder = "duygu_ek" if call_id.startswith("duygu_ek") else "calls"
    doc = json.loads((DATA / folder / f"{call_id}.json").read_text(encoding="utf-8"))
    segments, t = [], 0
    for idx, turn in enumerate(doc["turns"]):
        dur = max(1000, len(turn["text"]) * 65)  # yalnızca sıralama için yaklaşık süre
        segments.append(
            Segment(
                idx=idx, speaker=turn["speaker"], start_ms=t, end_ms=t + dur,
                text_masked=turn["text"],
            )
        )  # fmt: skip
        t += dur
    return AnalysisContext(call_id=uuid5(NAMESPACE_URL, f"synthetic/{call_id}"), segments=segments)


async def run_one(
    orchestrator: Orchestrator, call_id: str, label: dict[str, Any]
) -> dict[str, Any]:
    """Agent'ı üretimdeki gibi orkestratör üzerinden çalıştırır (doğrulama + tek düzeltme)."""
    outcome = await orchestrator.run(load_context(call_id))
    run = outcome.runs[0]
    return {
        "call_id": call_id,
        "truth": label,
        "status": run.status,
        "error": run.error,
        "attempts": run.attempts,
        "latency_ms": run.latency_ms,
        "tokens": run.tokens_in + run.tokens_out,
        "pred": outcome.outputs.get(SENTIMENT_ANALYZER),
    }


async def measure(call_ids: list[str], settings: Settings) -> list[dict[str, Any]]:
    labels = load_labels()
    orchestrator = Orchestrator(
        [[SentimentAnalyzerAgent(settings=settings)]], agent_timeout_s=settings.llm_agent_timeout_s
    )
    sem = asyncio.Semaphore(max(1, settings.llm_max_concurrency))

    async def guarded(cid: str) -> dict[str, Any]:
        async with sem:
            row = await run_one(orchestrator, cid, labels[cid])
        print(f"  {cid}: {row['status']} ({row['latency_ms'] / 1000:.1f} sn)", file=sys.stderr)
        return row

    return list(await asyncio.gather(*(guarded(c) for c in call_ids)))


def _rate(ok: int, total: int) -> str:
    return f"%{round(100 * ok / total)} ({ok}/{total})" if total else "-"


def report(rows: list[dict[str, Any]], settings: Settings) -> str:
    splits = load_splits()
    done = [r for r in rows if r["pred"] is not None]
    failed = [r for r in rows if r["pred"] is None]
    lines = [
        f"Model: smart={settings.llm_smart_model} | sağlayıcı={settings.llm_provider} "
        f"| çağrı={len(rows)} | agent başarısız={len(failed)}",
        "",
    ]

    def subset_rate(pred: Any) -> str:
        sub = [r for r in done if pred(r)]
        ok = sum(1 for r in sub if r["pred"]["sentiment"] == r["truth"]["sentiment"])
        return _rate(ok, len(sub))

    lines += [
        "| Küme | Duygu doğruluğu |",
        "|---|---|",
        f"| Tümü | {subset_rate(lambda r: True)} |",
        f"| Ana 100 çağrı | {subset_rate(lambda r: r['truth']['kume'] == 'ana')} |",
        f"| Ek 19 çağrı | {subset_rate(lambda r: r['truth']['kume'] == 'duygu_ek')} |",
        f"| Geliştirme kümesi (ana) | "
        f"{subset_rate(lambda r: splits.get(r['call_id']) == 'gelistirme')} |",
        f"| Test kümesi (ana) | {subset_rate(lambda r: splits.get(r['call_id']) == 'test')} |",
        f"| Sınır vakalar hariç | {subset_rate(lambda r: not r['truth']['zor'])} |",
        f"| Yalnızca sınır vakalar | {subset_rate(lambda r: r['truth']['zor'])} |",
        "",
        "Karışıklık tablosu (satır: doğru etiket, sütun: agent):",
        "",
        "| doğru \\ agent | " + " | ".join(CLASSES) + " | Doğru oran |",
        "|---|" + "---|" * (len(CLASSES) + 1),
    ]
    for truth in CLASSES:
        row = [r for r in done if r["truth"]["sentiment"] == truth]
        cells = [str(sum(1 for r in row if r["pred"]["sentiment"] == p)) for p in CLASSES]
        ok = sum(1 for r in row if r["pred"]["sentiment"] == truth)
        lines.append(f"| {truth} | " + " | ".join(cells) + f" | {_rate(ok, len(row))} |")

    # Şikâyet bayrağı: pozitif sınıf = şikâyet var.
    tp = sum(1 for r in done if r["truth"]["complaint"] and r["pred"]["complaint"])
    fp = sum(1 for r in done if not r["truth"]["complaint"] and r["pred"]["complaint"])
    fn = sum(1 for r in done if r["truth"]["complaint"] and not r["pred"]["complaint"])
    tn = len(done) - tp - fp - fn
    lines += [
        "",
        f"Şikâyet bayrağı: doğru pozitif {tp}, yanlış pozitif {fp}, kaçan {fn}, "
        f"doğru negatif {tn} | "
        f"duyarlılık {_rate(tp, tp + fn)} | kesinlik {_rate(tp, tp + fp)}",
    ]

    # Alıntı dayanağı ve güven
    quotes = [r for r in done if r["pred"]["evidence"]]
    lines.append(
        f"Alıntı veren çıktı: {len(quotes)}; ortalama güven: "
        f"{round(statistics.mean(r['pred']['confidence'] for r in done), 2) if done else '-'}"
    )
    fixes = sum(1 for r in rows if r["attempts"] > 1)
    lat = sorted(r["latency_ms"] for r in rows)
    if lat:
        p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
        lines.append(
            f"Düzeltme gereken çalışma: {fixes} | agent süresi: ortalama "
            f"{round(statistics.mean(lat) / 1000, 1)} sn, p95 {round(p95 / 1000, 1)} sn, "
            f"en uzun {round(lat[-1] / 1000, 1)} sn | "
            f"toplam token: {sum(r['tokens'] for r in rows)}"
        )

    wrong = [
        r
        for r in done
        if r["pred"]["sentiment"] != r["truth"]["sentiment"]
        or r["pred"]["complaint"] != r["truth"]["complaint"]
    ]
    if wrong:
        lines += ["", "Yanlış etiketlenenler:"]
        for r in wrong:
            t, p = r["truth"], r["pred"]
            lines.append(
                f"- {r['call_id']}{' (sınır)' if t['zor'] else ''}: doğru="
                f"{t['sentiment']}/{'şikâyet' if t['complaint'] else 'şikâyetsiz'}, agent="
                f"{p['sentiment']}/{'şikâyet' if p['complaint'] else 'şikâyetsiz'} "
                f"(güven {p['confidence']}) — {p['reason'][:110]}"
            )
    if failed:
        lines += [
            "",
            "Agent başarısız:",
            *(f"- {r['call_id']}: {(r['error'] or '')[:150]}" for r in failed),
        ]
    return "\n".join(lines)


async def duration_compare(n: int, settings: Settings, pause_s: float) -> str:
    """Aynı çağrılarda 4 agent ile 5 agent'ın uçtan uca süresi (sırayla, art arda)."""
    stages_all = default_stages(settings)
    without = [[a for a in stage if a.name != SENTIMENT_ANALYZER] for stage in stages_all]
    ids = [f"call_{i:03d}" for i in range(1, 101)][:: max(1, 100 // n)][:n]
    results: dict[str, list[float]] = {"4 agent": [], "5 agent": []}
    for cid in ids:
        for label, stages in (("4 agent", without), ("5 agent", stages_all)):
            orchestrator = Orchestrator(stages, agent_timeout_s=settings.llm_agent_timeout_s)
            started = time.perf_counter()
            outcome = await orchestrator.run(load_context(cid))
            results[label].append(time.perf_counter() - started)
            print(
                f"  {cid} {label}: {outcome.status} ({results[label][-1]:.1f} sn)", file=sys.stderr
            )
    lines = ["| Akış | Çağrı | Ortalama sn | Ortanca sn | En uzun sn |", "|---|---|---|---|---|"]
    for label, values in results.items():
        lines.append(
            f"| {label} | {len(values)} | {statistics.mean(values):.1f} | "
            f"{statistics.median(values):.1f} | {max(values):.1f} |"
        )
    delta = statistics.mean(results["5 agent"]) - statistics.mean(results["4 agent"])
    lines.append(f"\nFark (5 − 4 agent, ortalama): {delta:+.1f} sn/çağrı")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calls", help="virgülle ayrılmış çağrı kimlikleri (varsayılan: hepsi)")
    parser.add_argument("--smart", help="güçlü model adı (.env'i ezer)")
    parser.add_argument(
        "--sure", type=int, help="N çağrıda 4 agent ile 5 agent süresini karşılaştır"
    )
    parser.add_argument(
        "--ara", type=float, default=10.0, help="--sure çalıştırmaları arası bekleme (sn)"
    )
    parser.add_argument("--out", help="ham sonuçların yazılacağı JSON dosyası")
    parser.add_argument("--rapor", help="LLM çağırmadan, kaydedilmiş ham sonuçlardan rapor üret")
    args = parser.parse_args()

    settings = Settings(**({"llm_smart_model": args.smart} if args.smart else {}))
    if args.rapor:
        saved = json.loads(Path(args.rapor).read_text(encoding="utf-8"))
        print(report(saved, settings))
        return
    if args.sure:
        print(asyncio.run(duration_compare(args.sure, settings, args.ara)))
        return
    call_ids = args.calls.split(",") if args.calls else list(load_labels())
    rows = asyncio.run(measure(call_ids, settings))
    print(report(rows, settings))
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

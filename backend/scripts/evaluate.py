"""Agent'ları sentetik çağrılarda gerçek LLM ile çalıştırıp doğru etiketlerle karşılaştırır.

Kullanım (backend/ klasöründe, .env'de LLM ayarları dolu olmalı):

    python -m scripts.evaluate                                  # 10 çağrının hepsi
    python -m scripts.evaluate --calls call_001,call_004        # seçili çağrılar
    python -m scripts.evaluate --fast <model> --smart <model>   # .env'deki modelleri ez
    python -m scripts.evaluate --out sonuc.json                 # ham sonuçları da kaydet

Ücretsiz katmanların istek sınırı düşük olduğu için çağrılar sırayla işlenir.
Serbest metin alanları (problem, potansiyel iş) birebir değil, "boş mu dolu mu" olarak
karşılaştırılır; anlam karşılaştırması elle yapılır.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.agents.base import AnalysisContext, CallInfo, Segment
from app.agents.grounding import normalize
from app.agents.orchestrator import Orchestrator
from app.agents.registry import default_stages
from app.core.config import Settings
from app.schemas.analysis import AnalysisResult

DATA = Path(__file__).parents[2] / "data" / "synthetic"

ENUM_FIELDS = ["request_category", "service_mode", "urgency", "next_action"]
TEXT_FIELDS = ["problem", "potential_job"]


def load_context(call_id: str) -> AnalysisContext:
    doc = json.loads((DATA / "calls" / f"{call_id}.json").read_text(encoding="utf-8"))
    meta = next(
        m
        for m in json.loads((DATA / "calls_meta.json").read_text(encoding="utf-8"))
        if m["call_id"] == call_id
    )
    segments, t = [], 0
    for idx, turn in enumerate(doc["turns"]):
        # Metin uzunluğundan yaklaşık süre (saniyede ~15 karakter); yalnızca sıralama içindir.
        dur = max(1000, len(turn["text"]) * 65)
        segments.append(
            Segment(
                idx=idx,
                speaker=turn["speaker"],
                start_ms=t,
                end_ms=t + dur,
                text_masked=turn["text"],
            )
        )
        t += dur
    return AnalysisContext(
        call_id=uuid5(NAMESPACE_URL, f"synthetic/{call_id}"),
        segments=segments,
        call_info=CallInfo(
            started_at=meta["started_at"],
            answer_delay_s=meta["answer_delay_s"],
            duration_s=meta["duration_s"],
            outcome=meta["switchboard_outcome"],
        ),
    )


def load_truth(call_id: str) -> dict[str, Any]:
    truth: dict[str, Any] = json.loads(
        (DATA / "truth" / f"{call_id}.truth.json").read_text(encoding="utf-8")
    )
    return truth


def compare(truth: dict[str, Any], result: AnalysisResult) -> dict[str, bool | None]:
    """Alan → doğru mu (True/False); agent başarısızsa None."""
    scores: dict[str, bool | None] = {}
    cls = result.classification
    scores["call_type"] = None if cls is None else cls.call_type == truth["call_type"]

    crm = result.crm
    for f in ENUM_FIELDS:
        scores[f] = None if crm is None else getattr(crm, f) == truth["crm"][f]
    if crm is None:
        scores["location"] = None
    elif truth["crm"]["location"] is None:
        scores["location"] = crm.location is None
    else:
        expected = normalize(truth["crm"]["location"]).split()[0]
        scores["location"] = crm.location is not None and expected in normalize(crm.location)
    for f in TEXT_FIELDS:
        # Boş/dolu uyumu: konuşmada olmayanı uydurmuyor mu, olanı buluyor mu?
        scores[f + " (dolu/boş)"] = (
            None if crm is None else (getattr(crm, f) is None) == (truth["crm"][f] is None)
        )

    sales = result.sales
    scores["sales_outcome"] = None if sales is None else sales.outcome == truth["sales"]["outcome"]
    scores["loss_reason"] = (
        None if sales is None else sales.loss_reason == truth["sales"]["loss_reason"]
    )
    scores["summary (üretildi)"] = result.summary is not None
    return scores


async def run(call_ids: list[str], settings: Settings) -> list[dict[str, Any]]:
    orchestrator = Orchestrator(default_stages(settings))
    rows = []
    for cid in call_ids:
        started = time.perf_counter()
        outcome = await orchestrator.run(load_context(cid))
        result = outcome.to_analysis_result()
        rows.append(
            {
                "call_id": cid,
                "status": result.status,
                "seconds": round(time.perf_counter() - started, 1),
                "scores": compare(load_truth(cid), result),
                "attempts": {r.agent: r.attempts for r in result.runs},
                "errors": result.errors,
                "tokens": sum(r.tokens_in + r.tokens_out for r in result.runs),
                "output": result.model_dump(mode="json", exclude={"runs"}),
            }
        )
        print(f"  {cid}: {result.status} ({rows[-1]['seconds']} sn)", file=sys.stderr)
    return rows


def report(rows: list[dict[str, Any]], settings: Settings) -> str:
    fields = list(rows[0]["scores"])
    lines = [
        f"Model: fast={settings.llm_fast_model} | smart={settings.llm_smart_model} "
        f"| sağlayıcı={settings.llm_provider} | çağrı={len(rows)}",
        "",
        "| Alan | Doğru | Toplam | Oran |",
        "|---|---|---|---|",
    ]
    for f in fields:
        vals = [r["scores"][f] for r in rows]
        ok = sum(1 for v in vals if v is True)
        lines.append(f"| {f} | {ok} | {len(vals)} | %{round(100 * ok / len(vals))} |")
    total_ok = sum(1 for r in rows for v in r["scores"].values() if v is True)
    total = sum(len(r["scores"]) for r in rows)
    status = {s: sum(1 for r in rows if r["status"] == s) for s in ("tamam", "kismi", "basarisiz")}
    fixes = sum(1 for r in rows for a in r["attempts"].values() if a > 1)
    lines += [
        "",
        f"Genel doğruluk: %{round(100 * total_ok / total)} ({total_ok}/{total})",
        f"Analiz durumu: {status}",
        f"Düzeltme gereken agent çalışması: {fixes}",
        f"Ortalama süre: {round(sum(r['seconds'] for r in rows) / len(rows), 1)} sn/çağrı"
        f" | toplam token: {sum(r['tokens'] for r in rows)}",
    ]
    errors = {f"{r['call_id']}/{a}": e for r in rows for a, e in r["errors"].items()}
    if errors:
        lines += ["", "Hatalar:", *(f"- {k}: {v[:160]}" for k, v in errors.items())]
    wrong = [
        f"- {r['call_id']}: {', '.join(f for f, v in r['scores'].items() if v is False)}"
        for r in rows
        if any(v is False for v in r["scores"].values())
    ]
    if wrong:
        lines += ["", "Yanlış alanlar:", *wrong]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calls", help="virgülle ayrılmış çağrı kimlikleri (varsayılan: hepsi)")
    parser.add_argument("--fast", help="hızlı model adı (.env'i ezer)")
    parser.add_argument("--smart", help="güçlü model adı (.env'i ezer)")
    parser.add_argument("--out", help="ham sonuçların yazılacağı JSON dosyası")
    args = parser.parse_args()

    overrides = {}
    if args.fast:
        overrides["llm_fast_model"] = args.fast
    if args.smart:
        overrides["llm_smart_model"] = args.smart
    settings = Settings(**overrides)

    available = sorted(p.stem for p in (DATA / "calls").glob("call_*.json"))
    call_ids = args.calls.split(",") if args.calls else available

    rows = asyncio.run(run(call_ids, settings))
    print(report(rows, settings))
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

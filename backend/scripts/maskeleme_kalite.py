"""Maskelemenin analiz kalitesine etkisi: aynı çağrı ham ve maskeli metinle analiz edilir (#268).

Sentetik çağrılardaki `[İSİM]`/`[TELEFON]` yerlerine uydurma ad ve telefon konur, ilk müşteri
turuna uydurma adres, plaka ve kart eklenir ("ham" sürüm); "maskeli" sürüm bu metnin
`mask_text` çıktısıdır. İki sürüm de gerçek LLM ile analiz edilir ve doğru etiketlerle
(`data/synthetic/truth`) karşılaştırılır. Küçük örneklemdir (ücretsiz kota); sonuç yön
göstergesidir, istatistiksel iddia değildir.

Kullanım (backend/ klasöründe, .env'de LLM ayarları dolu olmalı):

    python -m scripts.maskeleme_kalite --calls call_001,call_002,call_008
"""

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any

from app.agents.base import AnalysisContext, Segment
from app.agents.orchestrator import Orchestrator
from app.agents.registry import default_stages
from app.core.config import Settings
from app.services.masking import mask_text
from scripts.evaluate import compare, load_context, load_truth

EK_CUMLE = (
    " Adresim Cumhuriyet Mahallesi 12. Sokak No 5, plakam 34 ABC 123, kartım 4539 1488 0343 6467."
)


def ham_surum(ctx: AnalysisContext) -> AnalysisContext:
    """Maskeli sentetik metne uydurma kişisel veri koyar."""
    segments = []
    eklendi = False
    for seg in ctx.segments:
        text = seg.text_masked.replace("[İSİM]", "Mehmet Yıldız")
        text = text.replace("[TELEFON]", "0532 123 45 67")
        if seg.speaker == "customer" and not eklendi:
            text += EK_CUMLE
            eklendi = True
        segments.append(seg.model_copy(update={"text_masked": text}))
    return ctx.model_copy(update={"segments": segments})


def maskeli_surum(ctx: AnalysisContext) -> AnalysisContext:
    segments: list[Segment] = [
        s.model_copy(update={"text_masked": mask_text(s.text_masked)}) for s in ctx.segments
    ]
    return ctx.model_copy(update={"segments": segments})


async def run(call_ids: list[str], settings: Settings) -> list[dict[str, Any]]:
    orchestrator = Orchestrator(
        default_stages(settings), agent_timeout_s=settings.llm_agent_timeout_s
    )
    rows = []
    for cid in call_ids:
        ham = ham_surum(load_context(cid))
        row: dict[str, Any] = {"call_id": cid}
        for ad, ctx in (("ham", ham), ("maskeli", maskeli_surum(ham))):
            outcome = await orchestrator.run(ctx)
            result = outcome.to_analysis_result()
            row[ad] = {
                "scores": compare(load_truth(cid), result),
                "summary": result.summary.summary if result.summary else None,
                "errors": result.errors,
                "gonderilen_metin": "\n".join(s.text_masked for s in ctx.segments),
            }
        rows.append(row)
    return rows


def ozet(rows: list[dict[str, Any]]) -> str:
    alanlar = sorted({k for r in rows for k in r["ham"]["scores"]})
    satirlar = ["| Alan | Ham doğru | Maskeli doğru |", "|---|---|---|"]
    toplam = {"ham": [0, 0], "maskeli": [0, 0]}
    for alan in alanlar:
        hucre = []
        for ad in ("ham", "maskeli"):
            degerler = [r[ad]["scores"].get(alan) for r in rows]
            olculen = [v for v in degerler if v is not None]
            dogru = sum(1 for v in olculen if v)
            toplam[ad][0] += dogru
            toplam[ad][1] += len(olculen)
            hucre.append(f"{dogru}/{len(olculen)}")
        satirlar.append(f"| {alan} | {hucre[0]} | {hucre[1]} |")
    satirlar.append(
        f"| **Toplam** | **{toplam['ham'][0]}/{toplam['ham'][1]}** "
        f"| **{toplam['maskeli'][0]}/{toplam['maskeli'][1]}** |"
    )
    for r in rows:
        satirlar.append(f"\n{r['call_id']} özet (ham): {r['ham']['summary']}")
        satirlar.append(f"{r['call_id']} özet (maskeli): {r['maskeli']['summary']}")
    return "\n".join(satirlar)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calls", required=True, help="virgülle ayrılmış çağrı kimlikleri")
    parser.add_argument("--out", help="ham sonuçların yazılacağı JSON dosyası")
    args = parser.parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = asyncio.run(run(args.calls.split(","), Settings()))
    print(ozet(rows))
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

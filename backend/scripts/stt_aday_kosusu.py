"""Tüm STT adaylarını aynı komutla, her biri ayrı süreçte koşar (#331, #332).

Ayrı süreç: tepe bellek ve model yükleme süresi adaylar arasında karışmaz. Sonuçlar
`--out-dir` altına `<aday>.json` yazılır, bitince Markdown özet tablo basılır.

Kullanım (backend/ klasöründe):

    uv run --extra stt --with torch --with transformers python -m scripts.stt_aday_kosusu \\
        --audio <ses klasörü> --out-dir <sonuç klasörü>
    ... --candidates medium,large-v3-turbo         # yalnız bazıları
    ... --skip groq-large-v3                       # (STT_API_KEY yoksa harici zaten atlanır)

Yalnız sentetik ses kullanın. Harici aday (Groq) için `STT_API_KEY` ortam değişkeni gerekir;
yoksa atlanır ve tabloda "anahtar yok" yazılır.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.stt.adaylar import CANDIDATES


def summarize_file(path: Path) -> dict[str, Any] | None:
    rows = [r for r in json.loads(path.read_text(encoding="utf-8")) if "error" not in r]
    if not rows:
        return None

    def mean(key: str) -> float | None:
        values = [r[key] for r in rows if r.get(key) is not None]
        return sum(values) / len(values) if values else None

    hit = sum(h for r in rows for h, _ in (r.get("terms") or {}).values())
    total = sum(t for r in rows for _, t in (r.get("terms") or {}).values())
    spk = [(r["wer_rep"] + r["wer_customer"]) / 2 for r in rows if r.get("wer_rep") is not None]
    audio = sum(r["duration_s"] for r in rows)
    return {
        "wer": mean("wer"),
        "wer_speaker": sum(spk) / len(spk) if spk else None,
        "terms": (hit, total),
        "rtf": sum(r["processing_s"] for r in rows) / audio if audio else None,
        "peak_mb": max((r["peak_mb"] or 0 for r in rows), default=None),
        "load_s": rows[0].get("load_s"),
        "files": len(rows),
    }


def fmt(value: float | None, pct: bool = False, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"%{100 * value:.{digits}f}" if pct else f"{value:.2f}"


def table(summaries: dict[str, dict[str, Any] | str]) -> str:
    lines = [
        "| Aday | WER | Konuşmacı WER | Terim doğruluğu | RTF | Tepe bellek | Model yükleme |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in summaries.items():
        if isinstance(s, str):
            lines.append(f"| {name} | {s} | | | | | |")
            continue
        hit, total = s["terms"]
        terms = f"%{100 * hit / total:.1f} ({hit}/{total})" if total else "—"
        peak = f"{s['peak_mb']:.0f} MB" if s["peak_mb"] else "—"
        load = f"{s['load_s']} sn" if s["load_s"] is not None else "—"
        lines.append(
            f"| {name} | {fmt(s['wer'], True)} | {fmt(s['wer_speaker'], True)} | {terms} | "
            f"{fmt(s['rtf'])} | {peak} | {load} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--candidates", help="Virgülle; boşsa hepsi")
    parser.add_argument("--skip", help="Virgülle atlanacak adaylar")
    parser.add_argument("--layout", default="stereo_rep_left")
    parser.add_argument("--force", action="store_true", help="Var olan sonucu yeniden koş")
    args = parser.parse_args()

    names = args.candidates.split(",") if args.candidates else list(CANDIDATES)
    skip = set(args.skip.split(",")) if args.skip else set()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, dict[str, Any] | str] = {}
    for name in names:
        if name not in CANDIDATES:
            sys.exit(f"Bilinmeyen aday: {name}")
        out = args.out_dir / f"{name}.json"
        if name in skip:
            summaries[name] = "atlandı"
            continue
        if CANDIDATES[name].external and not os.environ.get("STT_API_KEY"):
            summaries[name] = "anahtar yok (ölçülmedi)"
            continue
        if args.force or not out.exists():
            print(f"=== {name}", flush=True)
            cmd = [
                sys.executable,
                "-m",
                "scripts.stt_benchmark",
                "--audio",
                str(args.audio),
                "--candidate",
                name,
                "--beam",
                "1",
                "--layout",
                args.layout,
                "--out",
                str(out),
            ]
            proc = subprocess.run(cmd, check=False)
            if proc.returncode != 0 or not out.exists():
                summaries[name] = f"hata (çıkış {proc.returncode})"
                continue
        summary = summarize_file(out)
        summaries[name] = summary if summary else "sonuç yok"
    print("\n" + table(summaries))


if __name__ == "__main__":
    main()

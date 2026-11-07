"""Gerçek ekip kayıtlarını analiz eder: STT doğruluğu + 7 alan doğruluğu + süre (#150).

Kayıtları repoya koymayın (kişisel veri): repo dışı bir klasörde (ör. D:\\gercek_kayitlar) tutun.
Her kayıt için aynı adlı dosyalar:

    kayit_01.wav (veya .m4a/.mp3...)   zorunlu; stereo ise temsilci sol kanal
    kayit_01.txt                       isteğe bağlı: elle yazılmış doğru metin ("Temsilci: ..." /
                                       "Müşteri: ..." satırları) -> WER/CER
    kayit_01.truth.json                isteğe bağlı: beklenen alanlar (data/synthetic/truth ile aynı
                                       biçim) -> 7 alan doğruluğu

Kullanım (backend/ klasöründe, `--extra stt` ile):

    uv run --extra stt python -m scripts.real_recordings_eval --dir D:\\gercek_kayitlar
    uv run --extra stt python -m scripts.real_recordings_eval --dir D:\\kayitlar --layout mono
    uv run --extra stt python -m scripts.real_recordings_eval --dir D:\\gercek_kayitlar --stt-only

Çıktı: kayıt başına WER/CER, RTF, STT ve analiz süresi, alan doğrulukları; sonda Markdown tablo
(docs/stt_karari.md'ye yapıştırılabilir). `--out` ham sonucu JSON olarak da yazar.
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
from app.agents.orchestrator import Orchestrator
from app.agents.registry import default_stages
from app.core.config import Settings
from app.services.transcript_text import parse_transcript
from app.stt.base import SttError
from app.stt.metrics import cer, wer
from app.stt.pipeline import transcribe_call
from app.stt.registry import build_transcriber
from scripts.evaluate import compare
from scripts.stt_benchmark import AUDIO_EXT, peak_memory_mb

SEVEN_FIELDS = [
    "request_category",
    "location",
    "problem (dolu/boş)",
    "service_mode",
    "urgency",
    "potential_job (dolu/boş)",
    "next_action",
]


def reference(audio: Path) -> str | None:
    sidecar = audio.with_suffix(".txt")
    if not sidecar.exists():
        return None
    return " ".join(s.text for s in parse_transcript(sidecar.read_text(encoding="utf-8")))


def truth_for(audio: Path) -> dict[str, Any] | None:
    path = audio.with_name(f"{audio.stem}.truth.json")
    if not path.exists():
        return None
    truth: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return truth


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    settings = Settings()
    if args.model:
        settings = settings.model_copy(update={"whisper_model": args.model})
    layout = args.layout or settings.stt_channel_layout
    transcriber = build_transcriber(settings, settings.stt_provider)
    load = getattr(transcriber, "_get_model", None)
    if load is not None:
        load()
    orchestrator = Orchestrator(
        default_stages(settings), agent_timeout_s=settings.llm_agent_timeout_s
    )

    files = sorted(p for p in Path(args.dir).iterdir() if p.suffix.lower() in AUDIO_EXT)  # noqa: ASYNC240
    if not files:
        sys.exit(f"{args.dir} içinde ses dosyası yok ({', '.join(sorted(AUDIO_EXT))}).")
    rows: list[dict[str, Any]] = []
    for audio in files:
        row: dict[str, Any] = {"file": audio.name}
        try:
            result = await transcribe_call(
                audio, transcriber, layout=layout, language=settings.stt_language
            )
        except SttError as exc:
            row["error"] = str(exc)
            rows.append(row)
            print(f"  {audio.name}: STT HATA {exc}", file=sys.stderr)
            continue
        text = " ".join(t.text for t in result.turns)
        ref = reference(audio)
        row |= {
            "duration_s": round(result.duration_sec, 1),
            "stt_s": round(result.processing_s, 1),
            "rtf": round(result.processing_s / result.duration_sec, 2)
            if result.duration_sec
            else None,
            "wer": round(wer(ref, text), 3) if ref else None,
            "cer": round(cer(ref, text), 3) if ref else None,
            "text": text,
        }
        truth = truth_for(audio)
        if truth is not None and not args.stt_only:
            segments = [
                Segment(
                    idx=i,
                    speaker=t.speaker or "customer",
                    start_ms=t.start_ms,
                    end_ms=t.end_ms,
                    text_masked=t.text,
                )
                for i, t in enumerate(result.turns)
            ]
            context = AnalysisContext(
                call_id=uuid5(NAMESPACE_URL, f"gercek/{audio.stem}"),
                segments=segments,
                call_info=CallInfo(
                    started_at=truth.get("started_at", "2026-10-15T10:00:00+03:00"),
                    answer_delay_s=0,
                    duration_s=int(result.duration_sec),
                    outcome="answered",
                    marina=truth.get("marina"),
                ),
            )
            started = time.perf_counter()
            outcome = (await orchestrator.run(context)).to_analysis_result()
            row["analysis_s"] = round(time.perf_counter() - started, 1)
            row["status"] = outcome.status
            row["scores"] = compare(truth, outcome)
        rows.append(row)
        print(
            f"  {audio.name}: süre={row['duration_s']}s RTF={row['rtf']} WER={row['wer']} "
            f"analiz={row.get('analysis_s')}s",
            file=sys.stderr,
        )
    return rows


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def table(rows: list[dict[str, Any]]) -> str:
    ok = [r for r in rows if "error" not in r]
    lines = [
        "| Kayıt | Süre (sn) | STT (sn) | RTF | WER | CER | Analiz (sn) | 7 alan |",
        "|---|---|---|---|---|---|---|---|",
    ]
    totals: list[bool] = []
    for r in ok:
        scores = r.get("scores") or {}
        seven = [scores[f] for f in SEVEN_FIELDS if scores.get(f) is not None]
        totals += seven
        field = f"{sum(seven)}/{len(seven)}" if seven else "-"
        lines.append(
            f"| {r['file']} | {r['duration_s']} | {r['stt_s']} | {r['rtf']} | "
            f"{r['wer'] if r['wer'] is not None else '-'} | "
            f"{r['cer'] if r['cer'] is not None else '-'} | {r.get('analysis_s', '-')} | {field} |"
        )
    avg_wer = _mean([r["wer"] for r in ok if r["wer"] is not None])
    audio_s = sum(r["duration_s"] for r in ok)
    stt_s = sum(r["stt_s"] for r in ok)
    analysis = _mean([r["analysis_s"] for r in ok if "analysis_s" in r])
    lines.append(
        f"| **Toplam/ortalama** | {audio_s:.0f} | {stt_s:.0f} | {stt_s / max(1.0, audio_s):.2f} | "
        f"{'-' if avg_wer is None else round(avg_wer, 3)} | - | "
        f"{'-' if analysis is None else round(analysis, 1)} | "
        f"{'-' if not totals else f'%{100 * sum(totals) / len(totals):.0f}'} |"
    )
    return (
        "\n".join(lines)
        + f"\n\nTepe bellek: {peak_memory_mb()} MB; hatalı kayıt: {len(rows) - len(ok)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dir", required=True, help="Gerçek kayıt klasörü (repo dışı)")
    parser.add_argument("--layout", choices=["mono", "stereo_rep_left", "stereo_rep_right"])
    parser.add_argument("--model", help="faster-whisper model boyutu (.env'i ezer)")
    parser.add_argument("--stt-only", action="store_true", help="Yalnızca STT; analiz/LLM yok")
    parser.add_argument("--out", help="Ham sonuçları JSON olarak kaydet")
    args = parser.parse_args()
    rows = asyncio.run(run(args))
    print("\n" + table(rows))
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

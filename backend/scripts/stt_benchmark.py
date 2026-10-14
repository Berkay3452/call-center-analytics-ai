"""STT sağlayıcılarını aynı ses kayıtlarında karşılaştırır (#15): doğruluk ve hız.

Kullanım (backend/ klasöründe):

    python -m scripts.stt_benchmark --audio ../data/audio            # .env'deki sağlayıcı
    python -m scripts.stt_benchmark --audio ../data/audio --providers faster_whisper,stub
    python -m scripts.stt_benchmark --audio ../data/audio --model medium
    python -m scripts.stt_benchmark --audio ../data/audio --layout stereo_rep_left
    python -m scripts.stt_benchmark --audio ../data/audio --out stt_sonuc.json

Referans metin: ses dosyasıyla aynı adlı sentetik çağrı (`data/synthetic/calls/call_001.json`
→ `call_001.wav`) veya ses yanındaki `.txt`. Ölçütler:
- WER / CER: kelime ve karakter hata oranı (düşük iyi; maskeli adlar hesaba katılmaz)
- RTF: işlem süresi / ses süresi (1'den küçükse gerçek zamandan hızlı)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.transcript_text import parse_transcript
from app.stt.base import SttError
from app.stt.metrics import cer, wer
from app.stt.pipeline import transcribe_call
from app.stt.registry import build_transcriber

DATA = Path(__file__).parents[2] / "data" / "synthetic" / "calls"
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}


def reference_text(audio: Path) -> str | None:
    synthetic = DATA / f"{audio.stem}.json"
    if synthetic.exists():
        turns = json.loads(synthetic.read_text(encoding="utf-8"))["turns"]
        return " ".join(t["text"] for t in turns)
    sidecar = audio.with_suffix(".txt")
    if sidecar.exists():
        return " ".join(s.text for s in parse_transcript(sidecar.read_text(encoding="utf-8")))
    return None


def audio_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.suffix.lower() in AUDIO_EXT)


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    settings = Settings()
    overrides: dict[str, Any] = {}
    if args.model:
        overrides["whisper_model"] = args.model
    if overrides:
        settings = settings.model_copy(update=overrides)
    providers = args.providers.split(",") if args.providers else [settings.stt_provider]
    layout = args.layout or settings.stt_channel_layout

    rows: list[dict[str, Any]] = []
    for provider in providers:
        transcriber = build_transcriber(settings, provider)
        for audio in audio_files(Path(args.audio)):
            row: dict[str, Any] = {"provider": provider, "file": audio.name}
            try:
                result = await transcribe_call(
                    audio, transcriber, layout=layout, language=settings.stt_language
                )
            except SttError as exc:
                row["error"] = str(exc)
                rows.append(row)
                print(f"  {provider:18} {audio.name:20} HATA: {exc}")
                continue
            text = " ".join(t.text for t in result.turns)
            ref = reference_text(audio)
            row |= {
                "model": result.model,
                "duration_s": round(result.duration_sec, 1),
                "processing_s": round(result.processing_s, 1),
                "rtf": round(result.processing_s / result.duration_sec, 2)
                if result.duration_sec
                else None,
                "turns": len(result.turns),
                "wer": round(wer(ref, text), 3) if ref else None,
                "cer": round(cer(ref, text), 3) if ref else None,
                "text": text,
            }
            rows.append(row)
            print(
                f"  {provider:18} {audio.name:20} WER={row['wer']}  CER={row['cer']}  "
                f"RTF={row['rtf']}  süre={row['duration_s']}s  tur={row['turns']}"
            )
    return rows


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(rows: list[dict[str, Any]]) -> None:
    print("\nÖzet (ortalama):")
    for provider in dict.fromkeys(r["provider"] for r in rows):
        mine = [r for r in rows if r["provider"] == provider]
        ok = [r for r in mine if "error" not in r]
        wer_avg = _mean([r["wer"] for r in ok if r["wer"] is not None])
        rtf_avg = _mean([r["rtf"] for r in ok if r["rtf"] is not None])
        print(
            f"  {provider:18} dosya={len(ok)}  hata={len(mine) - len(ok)}"
            f"  WER={None if wer_avg is None else round(wer_avg, 3)}"
            f"  RTF={None if rtf_avg is None else round(rtf_avg, 2)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--audio", required=True, help="Ses dosyası veya klasörü")
    parser.add_argument("--providers", help="Virgülle: faster_whisper,openai_compatible,stub")
    parser.add_argument("--model", help="faster-whisper model boyutu (tiny/base/small/medium)")
    parser.add_argument("--layout", choices=["mono", "stereo_rep_left", "stereo_rep_right"])
    parser.add_argument("--out", help="Sonuçları JSON olarak kaydet")
    args = parser.parse_args()

    if not Path(args.audio).exists():
        sys.exit(f"Bulunamadı: {args.audio}")
    rows = asyncio.run(run(args))
    summarize(rows)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSonuçlar: {args.out}")


if __name__ == "__main__":
    main()

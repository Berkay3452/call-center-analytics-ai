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
- Bellek: sürecin tepe çalışma kümesi (MB); her modeli ayrı süreçte koşarak ölçün.
- Konuşmacı WER'i (`wer_rep`, `wer_customer`): her konuşmacının metni ayrı karşılaştırılır.
  Konuşmacılar doğru ayrılmazsa (ör. mono kayıt) bu değerler genel WER'den çok yüksek çıkar.
"""

import argparse
import asyncio
import json
import sys
import time
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


def peak_memory_mb() -> float | None:
    """Sürecin tepe bellek kullanımı (MB); ölçülemezse None. Modeller ayrı süreçte ölçülmeli."""
    try:
        import resource  # Linux/macOS

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1024 if sys.platform != "darwin" else 1024 * 1024), 0)
    except ImportError:
        pass
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    ]
    ok = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return round(counters.PeakWorkingSetSize / (1024 * 1024)) if ok else None


def reference_text(audio: Path) -> str | None:
    synthetic = DATA / f"{audio.stem}.json"
    if synthetic.exists():
        turns = json.loads(synthetic.read_text(encoding="utf-8"))["turns"]
        return " ".join(t["text"] for t in turns)
    sidecar = audio.with_suffix(".txt")
    if sidecar.exists():
        return " ".join(s.text for s in parse_transcript(sidecar.read_text(encoding="utf-8")))
    return None


def reference_by_speaker(audio: Path) -> dict[str, str] | None:
    """Sentetik çağrıda konuşmacı başına referans metin (`rep`, `customer`)."""
    synthetic = DATA / f"{audio.stem}.json"
    if not synthetic.exists():
        return None
    turns = json.loads(synthetic.read_text(encoding="utf-8"))["turns"]
    return {
        who: " ".join(t["text"] for t in turns if t["speaker"] == who)
        for who in ("rep", "customer")
    }


def audio_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.suffix.lower() in AUDIO_EXT)


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    settings = Settings()
    overrides: dict[str, Any] = {}
    if args.model:
        overrides["whisper_model"] = args.model
    if args.beam is not None:
        overrides["whisper_beam_size"] = args.beam
    if args.threads is not None:
        overrides["whisper_cpu_threads"] = args.threads
    if args.compute_type:
        overrides["whisper_compute_type"] = args.compute_type
    if args.vad_threshold is not None:
        overrides["whisper_vad_threshold"] = args.vad_threshold
    if overrides:
        settings = settings.model_copy(update=overrides)
    providers = args.providers.split(",") if args.providers else [settings.stt_provider]
    layout = args.layout or settings.stt_channel_layout

    rows: list[dict[str, Any]] = []
    for provider in providers:
        transcriber = build_transcriber(settings, provider)
        load_model = getattr(transcriber, "_get_model", None)
        load_s: float | None = None
        if load_model is not None:  # modeli ayrı yükle: soğuk başlangıç süresi (#163)
            loading = time.perf_counter()
            load_model()
            load_s = round(time.perf_counter() - loading, 1)
            print(f"  {provider:18} model yükleme: {load_s}s")
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
            by_speaker = reference_by_speaker(audio)
            hyp = {
                who: " ".join(t.text for t in result.turns if t.speaker == who)
                for who in ("rep", "customer")
            }
            row |= {
                "model": result.model,
                "load_s": load_s,
                "peak_mb": peak_memory_mb(),
                "duration_s": round(result.duration_sec, 1),
                "processing_s": round(result.processing_s, 1),
                "rtf": round(result.processing_s / result.duration_sec, 2)
                if result.duration_sec
                else None,
                "turns": len(result.turns),
                "wer": round(wer(ref, text), 3) if ref else None,
                "cer": round(cer(ref, text), 3) if ref else None,
                "wer_rep": round(wer(by_speaker["rep"], hyp["rep"]), 3) if by_speaker else None,
                "wer_customer": round(wer(by_speaker["customer"], hyp["customer"]), 3)
                if by_speaker
                else None,
                "text": text,
            }
            rows.append(row)
            print(
                f"  {provider:18} {audio.name:20} WER={row['wer']}  CER={row['cer']}  "
                f"WER(temsilci/müşteri)={row['wer_rep']}/{row['wer_customer']}  "
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
        spk = _mean(
            [(r["wer_rep"] + r["wer_customer"]) / 2 for r in ok if r.get("wer_rep") is not None]
        )
        peak = max((r["peak_mb"] for r in ok if r.get("peak_mb")), default=None)
        proc = sum(r["processing_s"] for r in ok)
        audio = sum(r["duration_s"] for r in ok)
        print(
            f"  {provider:18} dosya={len(ok)}  hata={len(mine) - len(ok)}"
            f"  toplam-RTF={round(proc / audio, 2) if audio else None}  tepe-bellek={peak} MB"
            f"  WER={None if wer_avg is None else round(wer_avg, 3)}"
            f"  konuşmacı-WER={None if spk is None else round(spk, 3)}"
            f"  RTF={None if rtf_avg is None else round(rtf_avg, 2)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--audio", required=True, help="Ses dosyası veya klasörü")
    parser.add_argument("--providers", help="Virgülle: faster_whisper,openai_compatible,stub")
    parser.add_argument("--model", help="faster-whisper model boyutu (tiny/base/small/medium)")
    parser.add_argument("--beam", type=int, help="WHISPER_BEAM_SIZE'ı ez (1 en hızlı)")
    parser.add_argument("--threads", type=int, help="WHISPER_CPU_THREADS'i ez (0: otomatik)")
    parser.add_argument("--compute-type", help="WHISPER_COMPUTE_TYPE'ı ez (int8, int8_float32...)")
    parser.add_argument("--vad-threshold", type=float, help="WHISPER_VAD_THRESHOLD'u ez")
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

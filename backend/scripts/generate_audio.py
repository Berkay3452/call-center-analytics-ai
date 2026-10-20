"""Seed çağrıları için sentetik ses üretir (#85): Türkçe, çevrimdışı Piper TTS.

`data/synthetic/calls/call_NNN.json` içindeki konuşma sıralarından `AUDIO_STORAGE_DIR/seed/` altına
`call_NNN.wav` ve gerçek tur zamanlarını içeren `call_NNN.timing.json` yazar. Ardından
`python -m scripts.seed` bu seslerin `calls.audio_path`'ini bağlar (transkript zaten hazırdır,
STT çalışmaz).

Kullanım (`backend/` klasöründe; Piper projenin bağımlılığı değildir, geçici eklenir):

    uv run --with piper-tts python -m scripts.generate_audio
    uv run --with piper-tts python -m scripts.generate_audio --calls call_001,call_004
    uv run --with piper-tts python -m scripts.generate_audio --mono     # tek kanal (eski biçim)

Ses modeli (`tr_TR-dfki-medium`, ~60 MB) ilk çalıştırmada `--voice-dir` klasörüne indirilir.
Varsayılan **stereo** (santral kaydı gibi): temsilci sol, müşteri sağ kanal; STT
`STT_CHANNEL_LAYOUT=stereo_rep_left` ile konuşmacıları kanaldan ayırır. Tek Türkçe Piper sesi
olduğu için müşteri sesinin perdesi yükseltilir (`--customer-pitch`), iki farklı kişi gibi duyulur.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.audio_ingest import storage_dir
from scripts.seed.audio import build_wav, write_seed_audio
from scripts.seed.generator import DATA_DIR

VOICE = "tr_TR-dfki-medium"
_VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium"
DEFAULT_VOICE_DIR = Path(__file__).resolve().parents[1] / "storage" / "tts"


def ensure_voice(voice_dir: Path) -> Path:
    """Piper ses modelini (onnx + json) yoksa indirir; model yolunu döner."""
    voice_dir.mkdir(parents=True, exist_ok=True)
    model = voice_dir / f"{VOICE}.onnx"
    for name in (f"{VOICE}.onnx", f"{VOICE}.onnx.json"):
        target = voice_dir / name
        if not target.is_file():
            print(f"İndiriliyor: {name} ...", flush=True)
            urllib.request.urlretrieve(f"{_VOICE_URL}/{name}", target)
    return model


def make_synth(model_path: Path) -> Any:
    """Piper'la (metin -> 16-bit mono PCM, örnekleme hızı) üreten fonksiyon döner."""
    try:
        from piper import PiperVoice
    except ImportError:
        sys.exit(
            "piper-tts kurulu değil. Şöyle çalıştırın:\n"
            "  uv run --with piper-tts python -m scripts.generate_audio"
        )
    voice = PiperVoice.load(str(model_path))
    rate = int(voice.config.sample_rate)

    def synth(text: str) -> tuple[bytes, int]:
        chunks = [c.audio_int16_bytes for c in voice.synthesize(text)]
        return b"".join(chunks), rate

    return synth


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed çağrıları için sentetik ses üretir (#85).")
    parser.add_argument("--calls", help="Virgülle ayrılmış çağrı kimlikleri (boşsa hepsi).")
    parser.add_argument(
        "--audio-dir", type=Path, help="Çıktı klasörü (varsayılan AUDIO_STORAGE_DIR)."
    )
    parser.add_argument(
        "--voice-dir", type=Path, default=DEFAULT_VOICE_DIR, help="Ses modeli klasörü."
    )
    parser.add_argument(
        "--mono", action="store_true", help="Tek kanal üret (varsayılan stereo: temsilci sol)."
    )
    parser.add_argument(
        "--customer-pitch",
        type=float,
        default=1.15,
        help="Müşteri sesinin perde çarpanı (1 = değişmez; varsayılan 1.15).",
    )
    parser.add_argument("--force", action="store_true", help="Var olan sesleri yeniden üret.")
    args = parser.parse_args()

    audio_dir = args.audio_dir or storage_dir(get_settings())
    wanted = set(args.calls.split(",")) if args.calls else None
    call_files = sorted((DATA_DIR / "calls").glob("call_*.json"))
    if wanted:
        call_files = [f for f in call_files if f.stem in wanted]
    if not call_files:
        sys.exit("Üretilecek çağrı bulunamadı.")

    synth = make_synth(ensure_voice(args.voice_dir))
    made = skipped = 0
    for path in call_files:
        call_id = path.stem
        target = audio_dir / "seed" / f"{call_id}.wav"
        if target.is_file() and not args.force:
            skipped += 1
            continue
        turns = json.loads(path.read_text(encoding="utf-8"))["turns"]
        wav, timing = build_wav(
            turns, synth, stereo=not args.mono, customer_pitch=args.customer_pitch
        )
        write_seed_audio(audio_dir, call_id, wav, timing)
        made += 1
        print(f"{call_id}: {len(turns)} tur, {timing[-1][1] / 1000:.0f} sn, {len(wav) // 1024} KB")
    print(f"\nBitti: {made} ses üretildi, {skipped} atlandı -> {audio_dir / 'seed'}")
    print("Şimdi bağlamak için: uv run python -m scripts.seed")


if __name__ == "__main__":
    main()

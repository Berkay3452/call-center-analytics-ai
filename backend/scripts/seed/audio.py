"""Seed çağrıları için sentetik ses: birleştirme yardımcıları ve seed'in okuduğu bilgiler (#85).

Ses üretimi (`scripts/generate_audio.py`, Piper TTS) ve seed yükleyicisi (`loader.py`) burayı
paylaşır. Burada TTS modeli veya veritabanı yoktur; yalnızca `wave` modülü kullanılır.

Dosya düzeni (ses klasörü = `AUDIO_STORAGE_DIR`):
- `seed/call_001.wav`          : konuşma sesi (16-bit PCM; mono veya stereo)
- `seed/call_001.timing.json`  : her konuşma sırasının gerçek başlangıç/bitiş süresi (ms)
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import wave
from array import array
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED_AUDIO_SUBDIR = "seed"
DEFAULT_GAP_MS = 500

# Metindeki maskeler konuşulabilir bir karşılığa çevrilir (ses "köşeli parantez" okumasın).
_SPOKEN_NAME = "Ahmet Bey"
_SPOKEN_PHONE = "sıfır beş yüz otuz iki, bir yüz on bir, yirmi iki, otuz üç"

# (16-bit mono PCM baytları, örnekleme hızı)
Synth = Callable[[str], tuple[bytes, int]]


@dataclass(frozen=True)
class SeedAudio:
    """Seed'in bir çağrıya bağladığı ses bilgisi."""

    relative_path: str  # ses klasörüne göre (ör. "seed/call_001.wav")
    sha256: str
    duration_s: int
    timing: list[tuple[int, int]] | None  # tur başına (başlangıç_ms, bitiş_ms)


def clean_for_speech(text: str) -> str:
    """Maskeleri ([İSİM], [TELEFON]) konuşulur hale getirir, kalan köşeli ifadeleri siler."""
    spoken = text.replace("[İSİM]", _SPOKEN_NAME).replace("[TELEFON]", _SPOKEN_PHONE)
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", spoken)).strip()


def build_wav(
    turns: Sequence[dict[str, Any]],
    synth: Synth,
    *,
    stereo: bool = False,
    gap_ms: int = DEFAULT_GAP_MS,
) -> tuple[bytes, list[tuple[int, int]]]:
    """Konuşma sıralarını tek WAV'da birleştirir; (wav baytları, tur başına (başlangıç, bitiş) ms).

    `stereo=True`: temsilci (`rep`) sol, müşteri (`customer`) sağ kanala konur; böylece
    `STT_CHANNEL_LAYOUT=stereo_rep_left` ile konuşmacılar ayrılabilir. Varsayılan mono.
    """
    chunks: list[tuple[str, bytes]] = []
    rate = 0
    for turn in turns:
        pcm, sr = synth(clean_for_speech(turn["text"]))
        if rate and sr != rate:
            raise ValueError("Tüm sıralar aynı örnekleme hızında olmalı.")
        rate = sr
        chunks.append((turn["speaker"], pcm))
    if not chunks:
        raise ValueError("Ses üretmek için en az bir konuşma sırası gerekir.")

    gap_frames = int(rate * gap_ms / 1000)
    cursor = 0  # şimdiye kadarki çerçeve (frame) sayısı
    timing: list[tuple[int, int]] = []
    samples = array("h")
    for speaker, pcm in chunks:
        mono = array("h")
        mono.frombytes(pcm)
        n = len(mono)
        if stereo:
            frames = array("h", bytes(4 * n))  # n çerçeve, sol+sağ, sıfırlarla dolu
            frames[0 if speaker == "rep" else 1 :: 2] = mono
            samples.extend(frames)
            samples.extend(array("h", bytes(4 * gap_frames)))
        else:
            samples.extend(mono)
            samples.extend(array("h", bytes(2 * gap_frames)))
        timing.append((round(cursor * 1000 / rate), round((cursor + n) * 1000 / rate)))
        cursor += n + gap_frames
    if sys.byteorder == "big":  # WAV little-endian'dır
        samples.byteswap()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2 if stereo else 1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue(), timing


def write_seed_audio(
    audio_dir: Path, call_id: str, wav: bytes, timing: Sequence[tuple[int, int]]
) -> Path:
    """WAV'ı ve gerçek tur zamanlarını `audio_dir/seed/` altına yazar."""
    target_dir = audio_dir / SEED_AUDIO_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    wav_path = target_dir / f"{call_id}.wav"
    wav_path.write_bytes(wav)
    (target_dir / f"{call_id}.timing.json").write_text(
        json.dumps([{"start_ms": s, "end_ms": e} for s, e in timing]), encoding="utf-8"
    )
    return wav_path


def load_seed_audio(audio_dir: Path | None, call_id: str) -> SeedAudio | None:
    """Çağrı için üretilmiş ses varsa bilgilerini okur; yoksa None (`audio_path` boş kalır)."""
    if audio_dir is None:
        return None
    wav_path = audio_dir / SEED_AUDIO_SUBDIR / f"{call_id}.wav"
    if not wav_path.is_file():
        return None
    data = wav_path.read_bytes()
    with wave.open(str(wav_path), "rb") as w:
        duration_s = round(w.getnframes() / w.getframerate())
    timing: list[tuple[int, int]] | None = None
    timing_path = wav_path.with_suffix(".timing.json")
    if timing_path.is_file():
        raw = json.loads(timing_path.read_text(encoding="utf-8"))
        timing = [(int(t["start_ms"]), int(t["end_ms"])) for t in raw]
    return SeedAudio(
        relative_path=f"{SEED_AUDIO_SUBDIR}/{call_id}.wav",
        sha256=hashlib.sha256(data).hexdigest(),
        duration_s=duration_s,
        timing=timing,
    )

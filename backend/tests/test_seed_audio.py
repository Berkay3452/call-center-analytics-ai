"""Seed ses yardımcıları (#85): birleştirme, zamanlama, stereo ayrımı ve seed'in okuduğu bilgi.

TTS modeli veya veritabanı gerekmez; sahte bir `synth` kullanılır.
"""

import hashlib
import io
import wave
from array import array
from pathlib import Path

import pytest

from scripts.seed.audio import (
    build_wav,
    clean_for_speech,
    load_seed_audio,
    write_seed_audio,
)

RATE = 1000  # 1 örnek = 1 ms: süre hesapları okunaklı olur


def fake_synth(text: str) -> tuple[bytes, int]:
    """Her karakter için 10 örnek (10 ms) sabit genlikli ses."""
    n = 10 * len(text)
    return array("h", [1000] * n).tobytes(), RATE


TURNS = [
    {"speaker": "rep", "text": "Merhaba"},  # 7 karakter -> 70 örnek
    {"speaker": "customer", "text": "Selam"},  # 5 karakter -> 50 örnek
]


def read_wav(data: bytes) -> tuple[int, int, array]:
    with wave.open(io.BytesIO(data), "rb") as w:
        samples = array("h")
        samples.frombytes(w.readframes(w.getnframes()))
        return w.getnchannels(), w.getframerate(), samples


def test_clean_for_speech_replaces_masks_and_drops_other_brackets() -> None:
    text = "Merhaba [İSİM], numaram [TELEFON]. [EMAIL] yazın"
    cleaned = clean_for_speech(text)
    assert "[" not in cleaned and "]" not in cleaned
    assert cleaned.startswith("Merhaba Ahmet Bey, numaram sıfır beş yüz")
    assert cleaned.endswith("yazın") and "  " not in cleaned


def test_mono_wav_has_gaps_and_real_timing() -> None:
    wav, timing = build_wav(TURNS, fake_synth, gap_ms=100)

    channels, rate, samples = read_wav(wav)
    assert (channels, rate) == (1, RATE)
    assert len(samples) == 70 + 100 + 50 + 100  # konuşma + boşluk + konuşma + boşluk
    assert timing == [(0, 70), (170, 220)]
    assert all(s == 0 for s in samples[70:170])  # boşluk sessiz
    assert samples[0] == 1000 and samples[170] == 1000


def test_stereo_puts_rep_on_left_and_customer_on_right() -> None:
    wav, timing = build_wav(TURNS, fake_synth, stereo=True, gap_ms=100)

    channels, _, samples = read_wav(wav)
    assert channels == 2
    left, right = samples[0::2], samples[1::2]
    assert len(left) == len(right) == 70 + 100 + 50 + 100
    assert left[0:70].count(1000) == 70 and right[0:70].count(1000) == 0  # temsilci: sol
    assert right[170:220].count(1000) == 50 and left[170:220].count(1000) == 0  # müşteri: sağ
    assert timing == [(0, 70), (170, 220)]


def test_build_wav_rejects_empty_conversation_and_mixed_rates() -> None:
    with pytest.raises(ValueError):
        build_wav([], fake_synth)

    rates = iter([1000, 2000])
    with pytest.raises(ValueError):
        build_wav(TURNS, lambda t: (b"\x00\x00" * 10, next(rates)))


def test_write_and_load_seed_audio_roundtrip(tmp_path: Path) -> None:
    wav, timing = build_wav(TURNS, fake_synth, gap_ms=100)
    path = write_seed_audio(tmp_path, "call_001", wav, timing)

    assert path == tmp_path / "seed" / "call_001.wav"
    info = load_seed_audio(tmp_path, "call_001")
    assert info is not None
    assert info.relative_path == "seed/call_001.wav"
    assert info.sha256 == hashlib.sha256(wav).hexdigest()
    assert info.timing == [(0, 70), (170, 220)]
    assert info.duration_s == round((70 + 100 + 50 + 100) / RATE)


def test_load_seed_audio_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_seed_audio(tmp_path, "call_999") is None
    assert load_seed_audio(None, "call_001") is None

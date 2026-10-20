"""Temiz sentetik sesi santral kaydına benzetir (#124): 8 kHz telefon bandı, gürültü, dalga.

STT'yi yalnızca temiz Piper sesiyle ölçmek iyimser kalır. Bu betik her kanalı ayrı bozar
(stereo düzeni korunur):
- 300–3400 Hz bant geçiren süzgeç ve 8 kHz örnekleme (dar bant telefon hattı),
- μ-law (G.711) nicemleme,
- belirli bir sinyal/gürültü oranında (SNR) beyaz + düşük frekanslı uğultu,
- yavaş ses seviyesi dalgalanması (±3 dB).

Kullanım (`backend/` klasöründe):

    uv run python -m scripts.telephone_audio --src storage/audio/seed --dst storage/audio/telefon
    uv run python -m scripts.telephone_audio --src ... --dst ... --snr 15 --calls call_001,call_031

Çıktı aynı adlı `.wav` (8 kHz, 16-bit) dosyalarıdır;
`scripts.stt_benchmark --audio <dst>` ile ölçülür.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

TARGET_RATE = 8000
BAND = (300.0, 3400.0)
MU = 255.0


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """(kanal x örnek, float32 -1..1) ve örnekleme hızı."""
    with wave.open(str(path), "rb") as w:
        channels, rate = w.getnchannels(), w.getframerate()
        if w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: yalnızca 16-bit PCM desteklenir")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return data.reshape(-1, channels).T.astype(np.float32) / 32768.0, rate


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(audio.shape[0])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.T.reshape(-1).tobytes())


def band_limit_resample(x: np.ndarray, rate: int) -> np.ndarray:
    """FFT ile 300–3400 Hz dışını keser ve 8 kHz'e yeniden örnekler."""
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / rate)
    spec[(freqs < BAND[0]) | (freqs > BAND[1])] = 0
    m = max(1, round(n * TARGET_RATE / rate))
    keep = m // 2 + 1
    return np.fft.irfft(spec[:keep], n=m) * (m / n)


def mu_law(x: np.ndarray) -> np.ndarray:
    """8 bit μ-law nicemleme ve geri açma (G.711 benzeri bozulma)."""
    enc = np.sign(x) * np.log1p(MU * np.abs(x)) / np.log1p(MU)
    q = np.round((enc + 1) / 2 * 255) / 255 * 2 - 1
    return np.sign(q) * ((1 + MU) ** np.abs(q) - 1) / MU


def degrade(audio: np.ndarray, rate: int, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    out = []
    for ch in audio:
        y = band_limit_resample(ch, rate)
        t = np.arange(len(y)) / TARGET_RATE
        y = y * 10 ** (3 * np.sin(2 * np.pi * 0.2 * t + rng.uniform(0, 6.28)) / 20)
        speech = y[np.abs(y) > 1e-3]
        power = float(np.mean(speech**2)) if speech.size else 1e-6
        noise = rng.normal(0, 1, len(y)) + 0.5 * np.sin(2 * np.pi * 50 * t)
        noise *= np.sqrt(power / (10 ** (snr_db / 10)) / np.mean(noise**2))
        out.append(mu_law(np.clip(y + noise, -1, 1)))
    return np.vstack(out).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sesi telefon hattına benzetir (#124).")
    parser.add_argument("--src", type=Path, required=True, help="Temiz .wav klasörü")
    parser.add_argument("--dst", type=Path, required=True, help="Bozulmuş seslerin klasörü")
    parser.add_argument("--snr", type=float, default=18.0, help="Sinyal/gürültü oranı (dB)")
    parser.add_argument("--calls", help="Virgülle ayrılmış çağrı kimlikleri (boşsa hepsi)")
    parser.add_argument("--seed", type=int, default=124, help="Gürültü tohumu (tekrarlanabilir)")
    args = parser.parse_args()

    wanted = set(args.calls.split(",")) if args.calls else None
    files = sorted(p for p in args.src.glob("call_*.wav") if not wanted or p.stem in wanted)
    if not files:
        sys.exit("Bozulacak ses bulunamadı.")
    args.dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    for path in files:
        audio, rate = read_wav(path)
        write_wav(args.dst / path.name, degrade(audio, rate, args.snr, rng), TARGET_RATE)
        print(f"{path.stem}: {audio.shape[0]} kanal, {audio.shape[1] / rate:.0f} sn", flush=True)
    print(f"\nBitti: {len(files)} ses -> {args.dst} (8 kHz, SNR {args.snr:g} dB)")


if __name__ == "__main__":
    main()

"""Test için küçük, geçerli ses dosyaları (gerçek ses ve kişisel veri içermez; 440 Hz sinüs)."""

import io
import math
import struct
import wave


def make_wav(seconds: float = 0.5, *, rate: int = 8000, channels: int = 1) -> bytes:
    """Geçerli bir 16 bit PCM WAV üretir."""
    frames = bytearray()
    for i in range(int(rate * seconds)):
        sample = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
        frames += struct.pack("<h", sample) * channels
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
    return buf.getvalue()

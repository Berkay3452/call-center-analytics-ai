"""STT sağlayıcı sözleşmesi.

Yerel Whisper (GPU/CPU) ve API tabanlı STT aynı arayüzü uygular; hangisinin kullanılacağı
STT_PROVIDER ortam değişkeniyle seçilir (donanım kararı netleşince).
"""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class Word(BaseModel):
    text: str
    start_ms: int
    end_ms: int
    probability: float | None = None


class TranscriptionResult(BaseModel):
    language: str
    duration_sec: float
    words: list[Word]
    model: str


class Transcriber(Protocol):
    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        """Ses dosyasını kelime zaman damgalı metne çevirir."""
        ...

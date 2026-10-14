"""STT sağlayıcı sözleşmesi (#15).

Her sağlayıcı (yerel faster-whisper, Whisper API'si, stub) aynı arayüzü uygular; hangisinin
kullanılacağı `STT_PROVIDER` ile seçilir (bkz. `app/stt/registry.py`). Sağlayıcı yalnızca
"bu ses dosyasında ne söylendi"yi döner; konuşmacıların ayrılması ve konuşma turlarına
dönüştürme `app/stt/pipeline.py`'dedir.
"""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.agents.base import Speaker


class SttError(Exception):
    """STT hatası. `transient=True`: ağ/kota gibi geçici hata, yeniden denenebilir."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


class SttSegment(BaseModel):
    """Sağlayıcının döndürdüğü zaman damgalı metin parçası."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    # Sağlayıcı konuşmacıyı biliyorsa (ör. stub veya konuşmacı ayıran bir API) doludur.
    speaker: Speaker | None = None


class TranscriptionResult(BaseModel):
    language: str
    duration_sec: float = Field(ge=0)
    segments: list[SttSegment]
    model: str

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


class Transcriber(Protocol):
    """Ses dosyasını zaman damgalı metne çevirir. Hata durumunda `SttError` fırlatır."""

    name: str

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        """Ses dosyasını metne çevirir."""
        ...

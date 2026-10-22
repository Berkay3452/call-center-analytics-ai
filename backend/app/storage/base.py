"""Ses depolama soyutlaması temel arayüzü (#121).

Tüm ses depolama sağlayıcıları (yerel dosya sistemi, Google Cloud Storage vb.)
bu arayüzü gerçekleştirir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from fastapi import status
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.errors import AppError


class AudioTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"


class UnsupportedAudioError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"


ALLOWED_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".webm"})

AUDIO_MEDIA_TYPES: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
}


def guess_media_type(path_or_filename: str) -> str:
    """Dosya uzantısına göre MIME türünü döner."""
    ext = Path(path_or_filename).suffix.lower()
    return AUDIO_MEDIA_TYPES.get(ext, "application/octet-stream")


def parse_range_header(range_header: str, total_length: int) -> tuple[int, int] | None:
    """HTTP Range başlığını çözümler (RFC 7233).

    Örnekler:
    - 'bytes=0-15' -> (0, 15)
    - 'bytes=100-' -> (100, total_length - 1)
    - 'bytes=-50'  -> (total_length - 50, total_length - 1)
    """
    if not range_header.startswith("bytes="):
        return None
    range_val = range_header[6:].strip()
    if "," in range_val:
        range_val = range_val.split(",")[0].strip()
    parts = range_val.split("-")
    if len(parts) != 2:
        return None
    start_str, end_str = parts[0].strip(), parts[1].strip()
    try:
        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str and not end_str:
            start = int(start_str)
            end = total_length - 1
        elif not start_str and end_str:
            suffix = int(end_str)
            start = max(0, total_length - suffix)
            end = total_length - 1
        else:
            return None
    except ValueError:
        return None

    if start > end or start >= total_length or start < 0:
        return None
    end = min(end, total_length - 1)
    return start, end


class StoredAudio(BaseModel):
    """Saklanan ses dosyasının üstverisi."""

    relative_path: str  # depolama köküne göre göreli yol / nesne anahtarı (ör. "3f2a....wav")
    sha256: str
    size_bytes: int


class AudioStorage(ABC):
    """Ses depolama sağlayıcıları için soyut temel sınıf."""

    @abstractmethod
    def save(
        self,
        source: BinaryIO,
        filename: str | None,
        *,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> StoredAudio:
        """Sesi içeriğin SHA-256 özetiyle saklar, boyut ve uzantıyı denetler."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Belirtilen yoldaki ses dosyasının var olup olmadığını denetler."""

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Belirtilen yoldaki ses dosyasını siler. Varsa silip True, yoksa False döner."""

    @abstractmethod
    def open(self, path: str) -> BinaryIO:
        """Ses dosyasını ikili okuma kipinde açar."""

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Ses dosyasının tüm içeriğini bayt dizisi olarak okur."""

    @abstractmethod
    @contextmanager
    def open_local_path(self, path: str) -> Iterator[Path]:
        """STT ve yerel araçlar için dosyanın yerel dosya sistemi yolunu sunar.

        Yerel depolamada doğrudan dosya yolunu verir; bulut depolamada geçici bir
        dosyaya indirir ve işlem bitince geçici dosyayı temizler.
        """

    @abstractmethod
    def get_response(self, path: str, range_header: str | None = None) -> Response:
        """Ses dosyasını HTTP üzerinden akıtmak için FastAPI/Starlette yanıtı döner.

        Range başlığı varsa 206 Partial Content ve Content-Range döner; yoksa 200 döner.
        """

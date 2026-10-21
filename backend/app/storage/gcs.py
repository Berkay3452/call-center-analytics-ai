"""Google Cloud Storage (GCS) ve sahte bulut ses depolama sağlayıcısı (#121).

GCS bağlantısı yer tutucu/sahte (test) olarak modellenir; üretimde Google Cloud Storage
istemcisi (`google-cloud-storage`) ile bağlanacak şekilde hazırlanmıştır.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import structlog
from fastapi.responses import Response

from app.core.errors import NotFoundError
from app.services.audio_ingest import AudioTooLargeError, UnsupportedAudioError
from app.storage.base import (
    ALLOWED_EXTENSIONS,
    AudioStorage,
    StoredAudio,
    guess_media_type,
    parse_range_header,
)

log = structlog.get_logger(__name__)
_CHUNK_SIZE = 1024 * 1024


def _validate_safe_key(key: str) -> str:
    """Yol dışına çıkma denetimi yapar; geçersizse 404 fırlatır."""
    raw = Path(key)
    if raw.is_absolute() or key.startswith(("/", "\\")) or ".." in raw.parts:
        raise NotFoundError("Geçersiz ses dosyası yolu.")
    return key


class GcsAudioStorage(AudioStorage):
    """Google Cloud Storage ses depolama sağlayıcısı (Yer tutucu / Sahte bulut)."""

    def __init__(
        self,
        bucket_name: str = "call-audio",
        project_id: str | None = None,
        credentials_file: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.credentials_file = credentials_file
        # Bellek içi nesne deposu (bulut simülasyonu)
        self._objects: dict[str, bytes] = {}

    def exists(self, path: str) -> bool:
        try:
            key = _validate_safe_key(path)
            return key in self._objects
        except NotFoundError:
            return False

    def delete(self, path: str) -> bool:
        try:
            key = _validate_safe_key(path)
            if key in self._objects:
                del self._objects[key]
                return True
            return False
        except NotFoundError:
            return False

    def save(
        self,
        source: BinaryIO,
        filename: str | None,
        *,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> StoredAudio:
        ext = Path(filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedAudioError(
                f"Desteklenmeyen ses biçimi: {ext or 'uzantısız'}. "
                f"İzin verilenler: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        digest = hashlib.sha256()
        buffer = bytearray()
        size = 0

        while chunk := source.read(_CHUNK_SIZE):
            size += len(chunk)
            if size > max_bytes:
                raise AudioTooLargeError(
                    f"Ses dosyası en fazla {max_bytes // (1024 * 1024)} MB olabilir."
                )
            digest.update(chunk)
            buffer.extend(chunk)

        if size == 0:
            raise UnsupportedAudioError("Ses dosyası boş.")

        key = f"{digest.hexdigest()}{ext}"
        self._objects[key] = bytes(buffer)
        log.info("storage.gcs.uploaded", bucket=self.bucket_name, key=key, size=size)
        return StoredAudio(relative_path=key, sha256=digest.hexdigest(), size_bytes=size)

    def open(self, path: str) -> BinaryIO:
        key = _validate_safe_key(path)
        data = self._objects.get(key)
        if data is None:
            raise NotFoundError("Ses dosyası bulunamadı.")
        return io.BytesIO(data)

    def read_bytes(self, path: str) -> bytes:
        key = _validate_safe_key(path)
        data = self._objects.get(key)
        if data is None:
            raise NotFoundError("Ses dosyası bulunamadı.")
        return data

    @contextmanager
    def open_local_path(self, path: str) -> Iterator[Path]:
        key = _validate_safe_key(path)
        data = self._objects.get(key)
        if data is None:
            raise NotFoundError("Ses dosyası bulunamadı.")

        ext = Path(key).suffix
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        try:
            yield tmp_path
        finally:
            tmp_path.unlink(missing_ok=True)

    def get_response(self, path: str, range_header: str | None = None) -> Response:
        key = _validate_safe_key(path)
        data = self._objects.get(key)
        if data is None:
            raise NotFoundError("Ses dosyası bulunamadı.")

        total_length = len(data)
        media_type = guess_media_type(key)

        if range_header:
            parsed = parse_range_header(range_header, total_length)
            if parsed is not None:
                start, end = parsed
                chunk = data[start : end + 1]
                return Response(
                    content=chunk,
                    status_code=206,
                    media_type=media_type,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{total_length}",
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(chunk)),
                    },
                )
            if range_header.startswith("bytes="):
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{total_length}"},
                )

        return Response(
            content=data,
            status_code=200,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(total_length),
            },
        )


class FakeGcsAudioStorage(GcsAudioStorage):
    """Testlerde ve yer tutucu senaryolarda kullanılan sahte GCS depolama sınıfı."""

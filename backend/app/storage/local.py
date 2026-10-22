"""Yerel dosya sistemi ses depolama sağlayıcısı (#121)."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from fastapi.responses import FileResponse, Response

from app.core.errors import NotFoundError
from app.storage.base import (
    ALLOWED_EXTENSIONS,
    AudioStorage,
    AudioTooLargeError,
    StoredAudio,
    UnsupportedAudioError,
    guess_media_type,
)

_CHUNK_SIZE = 1024 * 1024


class LocalAudioStorage(AudioStorage):
    """Yerel disk üzerinde ses dosyalarını saklayan ve sunan sağlayıcı."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Yol dışına çıkma (path traversal) denetimi yaparak mutlak dosya yolunu döner."""
        raw_path = Path(relative_path)
        if raw_path.is_absolute() or relative_path.startswith(("/", "\\")):
            raise NotFoundError("Geçersiz ses dosyası yolu.")

        target = (self.base_dir / raw_path).resolve()
        try:
            target.relative_to(self.base_dir)
        except ValueError as err:
            raise NotFoundError("Geçersiz ses dosyası yolu.") from err
        return target

    def exists(self, path: str) -> bool:
        try:
            file_path = self._resolve_safe_path(path)
            return file_path.is_file()
        except NotFoundError:
            return False

    def delete(self, path: str) -> bool:
        try:
            file_path = self._resolve_safe_path(path)
            if file_path.is_file():
                file_path.unlink()
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

        self.base_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        tmp = self.base_dir / f".yukleniyor-{os.getpid()}-{id(source)}{ext}"
        try:
            with tmp.open("wb") as out:
                while chunk := source.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > max_bytes:
                        raise AudioTooLargeError(
                            f"Ses dosyası en fazla {max_bytes // (1024 * 1024)} MB olabilir."
                        )
                    digest.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise UnsupportedAudioError("Ses dosyası boş.")
            name = f"{digest.hexdigest()}{ext}"
            tmp.replace(self.base_dir / name)
        finally:
            tmp.unlink(missing_ok=True)

        return StoredAudio(relative_path=name, sha256=digest.hexdigest(), size_bytes=size)

    def open(self, path: str) -> BinaryIO:
        file_path = self._resolve_safe_path(path)
        if not file_path.is_file():
            raise NotFoundError("Ses dosyası bulunamadı.")
        return file_path.open("rb")

    def read_bytes(self, path: str) -> bytes:
        file_path = self._resolve_safe_path(path)
        if not file_path.is_file():
            raise NotFoundError("Ses dosyası bulunamadı.")
        return file_path.read_bytes()

    @contextmanager
    def open_local_path(self, path: str) -> Iterator[Path]:
        file_path = self._resolve_safe_path(path)
        if not file_path.is_file():
            raise NotFoundError("Ses dosyası bulunamadı.")
        yield file_path

    def get_response(self, path: str, range_header: str | None = None) -> Response:
        file_path = self._resolve_safe_path(path)
        if not file_path.is_file():
            raise NotFoundError("Ses dosyası bulunamadı.")
        media_type = guess_media_type(file_path.name)
        # Starlette FileResponse, gelen Request Range başlığını otomatik olarak işler.
        return FileResponse(file_path, media_type=media_type)

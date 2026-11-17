"""Yüklenen ses dosyasının içerik doğrulaması (#270).

Uzantı ve MIME istemci beyanıdır; sahte olabilir. Bu modül dosyanın gerçekten ses olduğunu iki
adımda denetler: (1) sihirli baytlar (magic bytes) uzantıyla uyumlu mu, (2) kod çözücü (PyAV/libav,
`ffprobe`'un kullandığı aynı kütüphane) dosyayı açabiliyor, ses akışı var, süre sınırın altında
ve ilk paketler çözülüyor mu. PyAV (`stt` ekstrası) kurulu değilse yalnızca 1. adım uygulanır.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import structlog

from app.storage.base import AudioTooLongError, UnsupportedAudioError

log = structlog.get_logger(__name__)

_HEAD = 16


def _is_mp3(head: bytes) -> bool:
    return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)


def _is_aac(head: bytes) -> bool:
    return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF0) == 0xF0)


_MAGIC: dict[str, Callable[[bytes], bool]] = {
    ".wav": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WAVE",
    ".mp3": _is_mp3,
    ".m4a": lambda h: h[4:8] == b"ftyp",
    ".ogg": lambda h: h[:4] == b"OggS",
    ".flac": lambda h: h[:4] == b"fLaC",
    ".aac": _is_aac,
    ".webm": lambda h: h[:4] == b"\x1a\x45\xdf\xa3",
}


def magic_matches(head: bytes, ext: str) -> bool:
    check = _MAGIC.get(ext.lower())
    return bool(check and check(head))


def inspect_audio(path: Path, *, max_duration_s: float) -> None:
    """Kod çözücüyle dosyayı inceler; bozuksa 415, çok uzunsa 413 fırlatır."""
    try:
        import av
    except ImportError:
        log.warning("audio.validate.av_missing")
        return
    try:
        container = av.open(str(path))
    except Exception as exc:
        raise UnsupportedAudioError("Ses dosyası bozuk veya okunamıyor.") from exc
    try:
        if not container.streams.audio:
            raise UnsupportedAudioError("Dosyada ses akışı yok.")
        if container.duration is not None and container.duration / 1_000_000 > max_duration_s:
            raise AudioTooLongError(
                f"Ses kaydı en fazla {int(max_duration_s // 60)} dakika olabilir."
            )
        stream = container.streams.audio[0]
        try:
            for index, packet in enumerate(container.demux(stream)):
                if packet.size:
                    stream.codec_context.decode(packet)
                if index >= 8:
                    break
        except Exception as exc:
            raise UnsupportedAudioError("Ses dosyası bozuk: içerik çözülemiyor.") from exc
    finally:
        container.close()


def validate_audio_upload(
    source: BinaryIO, filename: str | None, *, max_bytes: int, max_duration_s: float
) -> None:
    """Yükleme akışını (aranabilir) doğrular ve başa sarar. Uzantı denetimi depolamada yapılır."""
    ext = Path(filename or "").suffix.lower()
    if ext not in _MAGIC:
        return  # desteklenmeyen uzantıyı depolama katmanı 415 ile reddeder
    source.seek(0, 2)
    size = source.tell()
    source.seek(0)
    if size > max_bytes:
        return  # boyut aşımını depolama katmanı 413 ile bildirir; büyük dosya çözülmez
    head = source.read(_HEAD)
    source.seek(0)
    if not head:
        return  # boş dosyayı depolama katmanı reddeder
    if not magic_matches(head, ext):
        raise UnsupportedAudioError(
            f"Dosya içeriği {ext} ses biçimiyle uyuşmuyor; dosya sahte uzantılı veya bozuk."
        )
    with tempfile.TemporaryDirectory(prefix="ses-dogrulama-") as tmp:
        probe = Path(tmp) / f"yukleme{ext}"
        with probe.open("wb") as out:
            shutil.copyfileobj(source, out)
        source.seek(0)
        inspect_audio(probe, max_duration_s=max_duration_s)

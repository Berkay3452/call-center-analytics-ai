"""Sesli çağrı alma ve yazıya çevirme (#49).

Akış: `store_audio` dosyayı diske yazar (adı içeriğin SHA-256 özeti; aynı ses iki kez yüklenmez)
→ `create_audio_call` çağrıyı `beklemede` olarak kaydeder → Celery `stt` kuyruğu
`run_transcription` ile sesi konuşmacı turlarına çevirip maskeli transkripti yazar → analiz
görevi (#48) başlar.

Depolama: geliştirmede yerel klasör (`AUDIO_STORAGE_DIR`); canlıya alma (Google Cloud) sırasında
bulut deposuna taşınacak. Yol veritabanında bu klasöre göre göreli tutulur.
"""

import hashlib
import os
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog
from fastapi import status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models.ai import Call
from app.schemas.api import AudioCallMeta, CallState
from app.services.call_ingest import set_state, store_segments
from app.stt.base import SttError, Transcriber
from app.stt.pipeline import ChannelLayout, transcribe_call

log = structlog.get_logger(__name__)

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
_CHUNK = 1024 * 1024
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def storage_dir(settings: Settings) -> Path:
    """Ses klasörü; göreli yol `backend/` klasörüne göredir (API ve işçi aynı yeri görür)."""
    path = Path(settings.audio_storage_dir)
    return path if path.is_absolute() else _BACKEND_DIR / path


class AudioTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"


class UnsupportedAudioError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"


class DuplicateAudioError(ConflictError):
    code = "duplicate_audio"


class StoredAudio(BaseModel):
    relative_path: str  # depolama klasörüne göre (ör. "3f2a....wav")
    sha256: str
    size_bytes: int


def store_audio(
    source: BinaryIO, filename: str | None, storage_dir: Path, *, max_bytes: int
) -> StoredAudio:
    """Yüklenen sesi parça parça okuyup diske yazar; boyut ve uzantıyı denetler.

    Dosya adı içeriğin özetidir: aynı ses tekrar yüklenirse aynı dosyanın üstüne yazılır.
    """
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedAudioError(
            f"Desteklenmeyen ses biçimi: {ext or 'uzantısız'}. "
            f"İzin verilenler: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    storage_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    tmp = storage_dir / f".yukleniyor-{os.getpid()}-{id(source)}{ext}"
    try:
        with tmp.open("wb") as out:
            while chunk := source.read(_CHUNK):
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
        tmp.replace(storage_dir / name)
    finally:
        tmp.unlink(missing_ok=True)
    return StoredAudio(relative_path=name, sha256=digest.hexdigest(), size_bytes=size)


async def create_audio_call(session: AsyncSession, meta: AudioCallMeta, audio: StoredAudio) -> UUID:
    """Sesli çağrıyı `beklemede` olarak kaydeder. Aynı ses daha önce yüklendiyse 409."""
    existing = await session.scalar(select(Call.id).where(Call.audio_sha256 == audio.sha256))
    if existing is not None:
        raise DuplicateAudioError(
            "Bu ses dosyası daha önce yüklendi.", details={"call_id": str(existing)}
        )
    call = Call(
        started_at=meta.started_at,
        duration_s=meta.duration_s,
        answer_delay_s=meta.answer_delay_s,
        switchboard_outcome=meta.switchboard_outcome.value if meta.switchboard_outcome else None,
        customer_name=meta.customer_name,
        customer_phone=meta.customer_phone,
        boat_name=meta.boat_name,
        boat_model=meta.boat_model,
        marina=meta.marina,
        audio_path=audio.relative_path,
        audio_sha256=audio.sha256,
        state="beklemede",
    )
    session.add(call)
    await session.flush()
    return call.id


async def get_call_audio_file(
    session: AsyncSession, call_id: UUID, settings: Settings
) -> tuple[Path, str]:
    """Çağrının ses dosyasını ve MIME türünü döndürür (#80).

    Çağrı yoksa, ses kaydı yoksa, dosya diskte bulunamazsa veya yol depolama
    klasörünün dışına çıkıyorsa (path traversal) NotFoundError (404) fırlatır.
    """
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")
    if not call.audio_path:
        raise NotFoundError("Çağrıya ait ses dosyası bulunamadı.")

    raw_path = Path(call.audio_path)
    if raw_path.is_absolute() or call.audio_path.startswith(("/", "\\")):
        raise NotFoundError("Geçersiz ses dosyası yolu.")

    base_dir = storage_dir(settings).resolve()
    file_path = (base_dir / raw_path).resolve()
    try:
        file_path.relative_to(base_dir)
    except ValueError as err:
        raise NotFoundError("Geçersiz ses dosyası yolu.") from err

    if not file_path.is_file():
        raise NotFoundError("Ses dosyası bulunamadı.")

    media_type = AUDIO_MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    return file_path, media_type


async def run_transcription(
    call_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    transcriber: Transcriber,
    *,
    storage_dir: Path,
    layout: ChannelLayout = "mono",
    language: str = "tr",
) -> CallState:
    """Çağrının sesini yazıya çevirip transkripti yazar.

    Başarılıysa `beklemede` döner (analiz kuyruğa alınabilir); hata olursa çağrı `basarisiz`
    olur, neden `calls.error`'a yazılır ve `basarisiz` döner. Hata fırlatılmaz.
    """
    async with session_factory() as session, session.begin():
        call = await session.get(Call, call_id)
        if call is None:
            raise NotFoundError("Çağrı bulunamadı.")
        if not call.audio_path:
            await set_state(session, call_id, "basarisiz", "Çağrının ses kaydı yok.")
            return "basarisiz"
        audio_path = storage_dir / call.audio_path
        names = [call.customer_name]
        known_duration = call.duration_s
        await set_state(session, call_id, "yaziya_cevriliyor")

    try:
        result = await transcribe_call(audio_path, transcriber, layout=layout, language=language)
        if not result.turns:
            raise SttError("Seste konuşma bulunamadı.")
    except SttError as exc:
        log.warning("stt.failed", call_id=str(call_id), error=str(exc), transient=exc.transient)
        async with session_factory() as session, session.begin():
            await set_state(session, call_id, "basarisiz", f"Yazıya çevirme başarısız: {exc}")
        return "basarisiz"
    except Exception as exc:
        log.exception("stt.crashed", call_id=str(call_id))
        async with session_factory() as session, session.begin():
            await set_state(session, call_id, "basarisiz", f"{type(exc).__name__}: {exc}"[:500])
        return "basarisiz"

    async with session_factory() as session, session.begin():
        await store_segments(session, call_id, result.to_segments(), names=names)
        if known_duration is None and result.duration_sec:
            await session.execute(
                update(Call).where(Call.id == call_id).values(duration_s=round(result.duration_sec))
            )
        await set_state(session, call_id, "beklemede")
    log.info(
        "stt.saved",
        call_id=str(call_id),
        turns=len(result.turns),
        model=result.model,
        processing_s=round(result.processing_s, 1),
    )
    return "beklemede"

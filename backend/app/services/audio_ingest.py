"""Sesli çağrı alma ve yazıya çevirme (#49, #121).

Akış: `store_audio` sesi AudioStorage arayüzü ile saklar (adı içeriğin SHA-256 özeti;
aynı ses iki kez yüklenmez) → `create_audio_call` çağrıyı `beklemede` olarak kaydeder
→ Celery `stt` kuyruğu `run_transcription` ile sesi konuşmacı turlarına çevirip maskeli
transkripti yazar → analiz görevi (#48) başlar.

Depolama: AudioStorage soyutlaması üzerinden yerel klasör (`AUDIO_STORAGE_DIR`) veya
bulut deposu (GCS) ile çalışır (#121).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.models.ai import Call
from app.schemas.api import AudioCallMeta, CallState
from app.services.call_ingest import set_state, store_segments
from app.storage.base import (  # noqa: F401 - hata sınıfları geriye uyumluluk için buradan da erişilir
    AUDIO_MEDIA_TYPES,
    AudioStorage,
    AudioTooLargeError,
    StoredAudio,
    UnsupportedAudioError,
)
from app.stt.base import SttError, Transcriber
from app.stt.pipeline import ChannelLayout, transcribe_call

log = structlog.get_logger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def storage_dir(settings: Settings) -> Path:
    """Ses klasörü; göreli yol `backend/` klasörüne göredir (API ve işçi aynı yeri görür)."""
    path = Path(settings.audio_storage_dir)
    return path if path.is_absolute() else _BACKEND_DIR / path


class DuplicateAudioError(ConflictError):
    code = "duplicate_audio"


def store_audio(
    source: BinaryIO,
    filename: str | None,
    storage: AudioStorage | Path | str | None = None,
    *,
    max_bytes: int,
) -> StoredAudio:
    """Yüklenen sesi AudioStorage arayüzü ile saklar; boyut ve uzantıyı denetler.

    Dosya adı içeriğin özetidir: aynı ses tekrar yüklenirse aynı dosyanın üstüne yazılır.
    Geriye dönük uyumluluk için `storage` parametresi Path, str veya AudioStorage alabilir.
    """
    from app.storage.local import LocalAudioStorage
    from app.storage.registry import build_audio_storage

    if isinstance(storage, AudioStorage):
        backend = storage
    elif isinstance(storage, (str, Path)):
        backend = LocalAudioStorage(storage)
    else:
        backend = build_audio_storage(get_settings())

    return backend.save(source, filename, max_bytes=max_bytes)


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
    """Çağrının yerel ses dosyasını ve MIME türünü döndürür (#80).

    Geriye dönük uyumluluk için korunmuştur.
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


async def get_call_audio_response(
    session: AsyncSession,
    call_id: UUID,
    storage: AudioStorage,
    *,
    range_header: str | None = None,
) -> Response:
    """Çağrının ses dosyasını AudioStorage arayüzü üzerinden akıtır (#80, #121).

    Çağrı yoksa veya ses kaydı yoksa 404 fırlatır. Range isteklerini (206) destekler.
    """
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFoundError("Çağrı bulunamadı.")
    if not call.audio_path:
        raise NotFoundError("Çağrıya ait ses dosyası bulunamadı.")

    return storage.get_response(call.audio_path, range_header=range_header)


async def run_transcription(
    call_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    transcriber: Transcriber,
    *,
    storage: AudioStorage | Path | str | None = None,
    storage_dir: Path | str | None = None,
    layout: ChannelLayout = "mono",
    language: str = "tr",
) -> CallState:
    """Çağrının sesini AudioStorage üzerinden okuyarak yazıya çevirir.

    Başarılıysa `beklemede` döner (analiz kuyruğa alınabilir); hata olursa çağrı `basarisiz`
    olur, neden `calls.error`'a yazılır ve `basarisiz` döner. Hata fırlatılmaz.
    """
    from app.storage.local import LocalAudioStorage
    from app.storage.registry import build_audio_storage

    if isinstance(storage, AudioStorage):
        active_storage = storage
    elif isinstance(storage, (str, Path)):
        active_storage = LocalAudioStorage(storage)
    elif storage_dir is not None:
        active_storage = LocalAudioStorage(storage_dir)
    else:
        active_storage = build_audio_storage(get_settings())

    async with session_factory() as session, session.begin():
        call = await session.get(Call, call_id)
        if call is None:
            raise NotFoundError("Çağrı bulunamadı.")
        if not call.audio_path:
            await set_state(session, call_id, "basarisiz", "Çağrının ses kaydı yok.")
            return "basarisiz"
        audio_key = call.audio_path
        # Yüklemeden STT görevinin başlamasına kadar geçen süre = kuyrukta bekleme (#162).
        queue_wait_s = round((datetime.now(UTC) - call.created_at).total_seconds(), 1)
        names = [call.customer_name]
        known_duration = call.duration_s
        await set_state(session, call_id, "yaziya_cevriliyor")

    try:
        with active_storage.open_local_path(audio_key) as audio_path:
            result = await transcribe_call(
                audio_path, transcriber, layout=layout, language=language
            )
            if not result.turns:
                raise SttError("Seste konuşma bulunamadı.")
    except NotFoundError as exc:
        log.warning("stt.audio_missing", call_id=str(call_id), error=str(exc))
        async with session_factory() as session, session.begin():
            await set_state(session, call_id, "basarisiz", str(exc))
        return "basarisiz"
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

    save_started = time.perf_counter()
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
        queue_wait_s=queue_wait_s,
        save_s=round(time.perf_counter() - save_started, 2),
    )
    return "beklemede"

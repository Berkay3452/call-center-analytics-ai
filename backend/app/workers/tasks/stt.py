"""Ses → metin görevi (kuyruk: stt). Bitince analiz görevi (kuyruk: analysis) kuyruğa alınır.

STT CPU'yu yoğun kullandığı için `stt` kuyruğu tek eşzamanlılıkla çalıştırılmalıdır; yerel
Whisper modeli işçi süreci boyunca bir kez yüklenir.
"""

from functools import lru_cache
from uuid import UUID

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.audio_ingest import run_transcription, storage_dir
from app.stt.base import Transcriber
from app.stt.registry import build_transcriber
from app.workers.celery_app import celery_app
from app.workers.tasks.analysis import analyze_call
from app.workers.utils import run_async


@lru_cache(maxsize=1)
def _transcriber() -> Transcriber:
    return build_transcriber(get_settings())


async def _transcribe(call_id: UUID) -> str:
    settings = get_settings()
    engine = create_engine(settings, null_pool=True)
    try:
        return await run_transcription(
            call_id,
            create_session_factory(engine),
            _transcriber(),
            storage_dir=storage_dir(settings),
            layout=settings.stt_channel_layout,
            language=settings.stt_language,
        )
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.tasks.stt.transcribe_audio")
def transcribe_audio(call_id: str) -> str:
    """Sesi yazıya çevirir; başarılıysa analizi başlatır. Nihai STT durumunu döner."""
    state = run_async(_transcribe(UUID(call_id)))
    if state == "beklemede":
        analyze_call.delay(call_id)
    return state

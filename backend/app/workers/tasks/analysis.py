"""Çağrı analizi görevi (kuyruk: analysis). LLM agent'ları burada çalışır."""

from uuid import UUID

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.call_ingest import run_call_analysis
from app.workers.celery_app import celery_app
from app.workers.utils import run_async


async def _analyze(call_id: UUID) -> str:
    # Görev başına kendi event loop'u olduğu için havuzsuz motor kullanılır (bkz. workers/utils).
    engine = create_engine(get_settings(), null_pool=True)
    try:
        return await run_call_analysis(call_id, create_session_factory(engine))
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.tasks.analysis.analyze_call")
def analyze_call(call_id: str) -> str:
    """Çağrıyı analiz eder; nihai durumu (`tamam`/`kismi`/`basarisiz`) döner.

    Hata olursa çağrının durumu `basarisiz` yapılır ve neden `calls.error`'a yazılır.
    """
    return run_async(_analyze(UUID(call_id)))

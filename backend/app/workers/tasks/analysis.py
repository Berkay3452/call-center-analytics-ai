"""Çağrı analizi görevi (kuyruk: analysis). LLM agent'ları burada çalışır."""

from uuid import UUID

import structlog

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.session import create_engine, create_session_factory
from app.services.call_ingest import run_call_analysis
from app.workers.celery_app import celery_app
from app.workers.utils import run_async

log = structlog.get_logger(__name__)


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
    Çağrı veritabanında bulunamazsa (eski/yetim görev) hata fırlatmaz, loglar ve
    'bulunamadi' döner (#107).
    """
    try:
        uid = UUID(call_id)
    except (ValueError, AttributeError):
        log.warning("call.orphan_task_skipped", call_id=call_id, reason="invalid_uuid")
        return "bulunamadi"

    try:
        return run_async(_analyze(uid))
    except NotFoundError:
        log.warning("call.orphan_task_skipped", call_id=call_id, reason="call_not_found")
        return "bulunamadi"

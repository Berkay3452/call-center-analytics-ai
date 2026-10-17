"""Sistem görevleri: işçinin ayakta olduğunu ve periyodik kurtarma işlemlerini yönetir."""

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.call_recovery import recover_stuck_calls
from app.workers.celery_app import celery_app
from app.workers.utils import run_async


@celery_app.task(name="app.workers.tasks.system.ping")
def ping() -> str:
    return "pong"


async def _recover_stuck_calls() -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings, null_pool=True)
    try:
        return await recover_stuck_calls(
            create_session_factory(engine),
            timeout_min=settings.stuck_call_timeout_min,
        )
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.tasks.system.recover_stuck_calls")
def recover_stuck_calls_task() -> dict[str, int]:
    """Zaman aşımına uğramış çağrıları kurtarır (#107)."""
    return run_async(_recover_stuck_calls())

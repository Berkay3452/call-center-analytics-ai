"""Celery uygulaması ve kuyruk yapılandırması.

Kuyruklar (mimari dokümanı §5.1):
- stt      : ses → transkript. CPU/GPU ağır; eşzamanlılık 1.
- analysis : LLM ajanları. I/O ağırlıklı; yüksek eşzamanlılık.
- index    : RAG chunk + embedding.
- default  : küçük sistem görevleri.

Çalıştırma (backend/ klasöründen):
    uv run celery -A app.workers.celery_app worker -Q default,analysis,index --pool=solo -l info
Not: Windows'ta Celery'nin prefork havuzu desteklenmez; geliştirmede `--pool=solo` kullanılır.
"""

import structlog
from celery import Celery
from celery.signals import worker_ready
from kombu import Queue

from app.core.config import get_settings

settings = get_settings()
log = structlog.get_logger(__name__)

celery_app = Celery(
    "call_center",
    broker=settings.broker_url,
    backend=settings.result_backend_url,
    include=[
        "app.workers.tasks.system",
        "app.workers.tasks.analysis",
        "app.workers.tasks.stt",
    ],
)

celery_app.conf.update(
    # Serileştirme: yalnızca JSON (pickle güvenlik riski taşır).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,
    # Dayanıklılık: görev bitmeden işçi ölürse görev kuyruğa geri döner.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Sonuçlar kısa süre tutulur; asıl çıktı veritabanına yazılır.
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("stt"),
        Queue("analysis"),
        Queue("index"),
    ),
    # Görev adı → kuyruk eşlemesi. Görev modülleri eklendikçe burası güncellenir.
    task_routes={
        "app.workers.tasks.stt.*": {"queue": "stt"},
        "app.workers.tasks.analysis.*": {"queue": "analysis"},
        "app.workers.tasks.index.*": {"queue": "index"},
    },
    # Periyodik görevler (#107): Takılı kalan çağrıları dakikada bir tarar.
    beat_schedule={
        "recover-stuck-calls": {
            "task": "app.workers.tasks.system.recover_stuck_calls",
            "schedule": 60.0,
        },
    },
)


@worker_ready.connect
def on_worker_ready(sender: object, **kwargs: object) -> None:
    """İşçi ayağa kalktığında hemen bir takılı çağrı taraması başlatır (#107)."""
    try:
        from app.workers.tasks.system import recover_stuck_calls_task

        recover_stuck_calls_task.delay()
        log.info("celery.worker_ready.stuck_calls_recovery_dispatched")
    except Exception as exc:
        log.warning("celery.worker_ready.dispatch_failed", error=str(exc))

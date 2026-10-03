"""Sistem görevleri: işçinin ayakta olduğunu ve kuyruğun çalıştığını doğrulamak için."""

from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.system.ping")
def ping() -> str:
    return "pong"

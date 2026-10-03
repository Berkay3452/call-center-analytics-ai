"""Görevler için ortak yardımcılar ve hata sınıfları."""

import asyncio
from collections.abc import Coroutine
from typing import Any


class TransientError(Exception):
    """Geçici hata (ağ, 429 oran sınırı, 5xx). Görev otomatik yeniden denenir."""


class PermanentError(Exception):
    """Kalıcı hata (bozuk ses dosyası, desteklenmeyen format). Yeniden denenmez → status=failed."""


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Celery görevleri senkrondur; async kodu görev başına TEK bir event loop'ta çalıştırır.

    Görev içinde veritabanı için `app.db.session.worker_session` kullanılmalı
    (havuzsuz motor — döngüler arası bağlantı sızıntısını önler).
    """
    return asyncio.run(coro)

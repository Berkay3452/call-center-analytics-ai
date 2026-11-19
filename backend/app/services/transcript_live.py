"""Canlı transkript akışı (#324): Redis Stream'indeki STT olaylarını SSE olarak iletir.

Yazan taraf `app/services/transcript_stream.py` (işçi). Bu modül yalnızca okur.

Davranış:
- Akış varsa baştan (ya da `Last-Event-ID`'den sonra) okunur; geç bağlanan istemci kaçırdığını alır.
- Akış bitince (`done`/`error`) bağlantı kapanır. Akış yoksa ve çağrı zaten bitmişse tek `done`
  (ya da `error`) olayı gönderilip kapanır; ön yüz kayıtlı transkripte döner.
- Bağlantı süresi (`max_s`) ve çağrı başına eşzamanlı bağlantı sayısı sınırlıdır.
- Akıştaki metin **ham** transkripttir; yalnız yönetici bağlamına açılır (uç `AdminCallerDep`),
  günlüğe yazılmaz.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette.sse import ServerSentEvent

from app.core.errors import NotFoundError, TooManyRequestsError
from app.db.models.ai import Call
from app.services.transcript_stream import ERROR_CODE, stream_key

log = structlog.get_logger(__name__)

# Uygulama Redis istemcisinin soket zaman aşımı (varsayılan 2 sn) bloklu okumadan uzun olmalı.
BLOCK_MS = 1000
BATCH = 100
MAX_CONNECTIONS_PER_CALL = 5
MAX_DURATION_S = 2700  # 45 dk; en uzun kabul edilen ses (120 dk) ~24 dk'da çözülür
# STT bittikten sonraki durumlar. `beklemede` belirsizdir (STT öncesi de sonrası da), bu yüzden
# yalnızca akıştaki `done` olayı ya da `isleniyor`'a geçiş STT'nin bittiğini gösterir.
FINISHED_STATES = frozenset({"isleniyor", "tamam", "kismi", "basarisiz"})
_TERMINAL = frozenset({"done", "error"})


def conn_key(call_id: UUID) -> str:
    return f"transcript:conn:{call_id}"


async def call_state(session_factory: async_sessionmaker[AsyncSession], call_id: UUID) -> str:
    """Çağrının durumu; yoksa `NotFoundError`. Kısa ömürlü oturum (akış boyunca tutulmaz)."""
    async with session_factory() as session:
        call = await session.get(Call, call_id)
        if call is None:
            raise NotFoundError("Çağrı bulunamadı.")
        return str(call.state)


def _event(event_id: str | None, name: str, data: dict[str, Any]) -> ServerSentEvent:
    return ServerSentEvent(
        data=json.dumps(data, ensure_ascii=False), event=name, id=event_id, retry=3000
    )


def _decode(fields: dict[Any, Any]) -> dict[str, Any]:
    out = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in fields.items()
    }
    for key in ("seq", "start_ms", "end_ms"):
        if key in out:
            try:
                out[key] = int(out[key])
            except (TypeError, ValueError):
                out.pop(key, None)
    return out


async def acquire_connection(redis: Redis, call_id: UUID) -> None:
    """Çağrı başına eşzamanlı bağlantı sınırı; aşımda 429."""
    key = conn_key(call_id)
    count = int(await redis.incr(key))
    await redis.expire(key, MAX_DURATION_S + 60)  # çöken sunucuda sayaç kendiliğinden düşer
    if count > MAX_CONNECTIONS_PER_CALL:
        await release_connection(redis, call_id)
        raise TooManyRequestsError("Bu çağrı için çok fazla canlı izleyici var.", retry_after_s=5)


async def release_connection(redis: Redis, call_id: UUID) -> None:
    try:
        left = int(await redis.decr(conn_key(call_id)))
        if left <= 0:
            await redis.delete(conn_key(call_id))
    except Exception:
        log.warning("transcript_live.release_failed")


async def stream_transcript(
    redis: Redis,
    session_factory: async_sessionmaker[AsyncSession],
    call_id: UUID,
    *,
    last_event_id: str | None = None,
    max_s: float | None = None,
    block_ms: int | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """SSE olayları üretir: `segment` ... sonra `done`/`error`; süre aşımında `timeout`."""
    key = stream_key(call_id)
    last = last_event_id if last_event_id and _valid_id(last_event_id) else "0"
    deadline = time.monotonic() + (MAX_DURATION_S if max_s is None else max_s)
    block = BLOCK_MS if block_ms is None else block_ms
    first = True
    while True:
        resp = await redis.xread({key: last}, count=BATCH, block=None if first else block)
        first = False
        if resp:
            for _name, entries in resp:
                for entry_id, fields in entries:
                    entry_id = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
                    last = entry_id
                    data = _decode(fields)
                    kind = str(data.pop("type", "segment"))
                    if kind == "error":
                        data = {"code": ERROR_CODE}  # ham hata ayrıntısı asla iletilmez
                    yield _event(entry_id, kind, data)
                    if kind in _TERMINAL:
                        return
            continue
        # Yeni olay yok: çağrı akış olmadan bitmiş olabilir (yayın kapalı, Redis hatası vb.).
        state = await call_state(session_factory, call_id)
        if state in FINISHED_STATES:
            if state == "basarisiz":
                yield _event(None, "error", {"code": ERROR_CODE})
            else:
                yield _event(None, "done", {"state": state})
            return
        if time.monotonic() >= deadline:
            yield _event(None, "timeout", {"state": state})
            return
        await asyncio.sleep(0)  # iptale (istemci koptu) izin ver


def _valid_id(value: str) -> bool:
    """Redis Stream kimliği (`<ms>-<seq>`); başka değer yok sayılır."""
    head, sep, tail = value.partition("-")
    return bool(sep) and head.isascii() and head.isdigit() and tail.isascii() and tail.isdigit()

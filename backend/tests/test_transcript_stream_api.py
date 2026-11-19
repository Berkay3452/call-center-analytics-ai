"""Canlı transkript SSE ucu (#324): GET /calls/{id}/transcript/stream.

Redis ve veritabanı sahtelenir. Akış sırası, `Last-Event-ID` ile devam, bitiş olayları, yetki,
404, bağlantı sınırı ve denetim kaydı doğrulanır.
"""

import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.core.security import sign_user_id
from app.db.models.ai import Call
from app.main import create_app
from app.services import transcript_live
from app.services.transcript_stream import stream_key
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

CALL_ID = UUID("22222222-2222-4222-8222-222222222222")
HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


class FakeRedis:
    """xread/incr/decr/expire/delete'in küçük sahtesi."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.entries: list[tuple[str, dict[str, Any]]] = [
            (f"{1000 + i}-0", e) for i, e in enumerate(events or [])
        ]
        self.counters: dict[str, int] = {}

    async def xread(self, streams: dict[str, str], count: int = 100, block: Any = None) -> Any:
        ((key, last),) = streams.items()
        assert key == stream_key(CALL_ID)
        new = [(i, f) for i, f in self.entries if _gt(i, last)][:count]
        return [(key, new)] if new else []

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def decr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) - 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self.counters.pop(key, None)

    async def aclose(self) -> None:
        return None


def _gt(entry_id: str, last: str) -> bool:
    a = tuple(int(x) for x in entry_id.split("-"))
    b = tuple(int(x) for x in last.split("-"))
    return a > b


class FakeSession:
    def __init__(self, call: Call | None) -> None:
        self.call = call
        self.added: list[Any] = []
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def scalar(self, stmt: Any) -> None:
        return None  # yakın zamanlı denetim kaydı yok

    async def get(self, model: type[Any], ident: Any) -> Any:
        return self.call if self.call is not None and self.call.id == ident else None


def seg(seq: int, speaker: str, text: str) -> dict[str, Any]:
    return {
        "type": "segment",
        "seq": str(seq),
        "speaker": speaker,
        "start_ms": str(seq * 1000),
        "end_ms": str(seq * 1000 + 900),
        "text": text,
    }


def make_call(state: str) -> Call:
    return Call(id=CALL_ID, started_at=datetime.now(UTC), state=state)


def _factory(fake: FakeSession) -> Any:
    return lambda: fake


async def _client(
    app: FastAPI, redis: FakeRedis, call: Call | None, session: FakeSession | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client_for(app):
        fake = session or FakeSession(call)
        app.state.redis = redis
        app.state.session_factory = _factory(fake)
        yield client


def parse_sse(text: str) -> list[tuple[str, dict[str, Any], str | None]]:
    out: list[tuple[str, dict[str, Any], str | None]] = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        name, data, ident = "message", "", None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
            elif line.startswith("id:"):
                ident = line[3:].strip()
        if data:
            out.append((name, json.loads(data), ident))
    return out


async def test_streams_segments_in_order_then_done() -> None:
    redis = FakeRedis(
        [
            seg(1, "rep", "Miço Usta, buyurun."),
            seg(2, "customer", "Motor tekliyor."),
            {"type": "done", "seq": "3"},
        ]
    )
    async for client in _client(create_app(make_settings()), redis, make_call("yaziya_cevriliyor")):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-store"
    events = parse_sse(resp.text)
    assert [e[0] for e in events] == ["segment", "segment", "done"]
    assert events[0][1] == {
        "seq": 1,
        "speaker": "rep",
        "start_ms": 1000,
        "end_ms": 1900,
        "text": "Miço Usta, buyurun.",
    }
    assert events[1][1]["speaker"] == "customer"
    assert [e[2] for e in events] == ["1000-0", "1001-0", "1002-0"]  # Last-Event-ID kaynağı


async def test_last_event_id_resumes_after_given_event() -> None:
    redis = FakeRedis([seg(1, "rep", "bir"), seg(2, "customer", "iki"), {"type": "done"}])
    async for client in _client(create_app(make_settings()), redis, make_call("yaziya_cevriliyor")):
        resp = await client.get(
            f"/api/v1/calls/{CALL_ID}/transcript/stream",
            headers={**HEADERS, "Last-Event-ID": "1000-0"},
        )

    assert [(e[0], e[1].get("text")) for e in parse_sse(resp.text)] == [
        ("segment", "iki"),
        ("done", None),
    ]


async def test_garbage_last_event_id_is_ignored() -> None:
    redis = FakeRedis([seg(1, "rep", "bir"), {"type": "done"}])
    async for client in _client(create_app(make_settings()), redis, make_call("yaziya_cevriliyor")):
        resp = await client.get(
            f"/api/v1/calls/{CALL_ID}/transcript/stream",
            headers={**HEADERS, "Last-Event-ID": "$; DROP"},
        )

    assert [e[0] for e in parse_sse(resp.text)] == ["segment", "done"]  # baştan okunur


async def test_error_event_carries_only_fixed_code() -> None:
    redis = FakeRedis(
        [{"type": "error", "seq": "1", "code": "stt_failed", "detail": "C:\\gizli.wav"}]
    )
    async for client in _client(create_app(make_settings()), redis, make_call("yaziya_cevriliyor")):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    ((name, data, _),) = parse_sse(resp.text)
    assert (name, data) == ("error", {"code": "stt_failed"})
    assert "gizli" not in resp.text


@pytest.mark.parametrize(
    ("state", "expected"),
    [("tamam", "done"), ("kismi", "done"), ("isleniyor", "done"), ("basarisiz", "error")],
)
async def test_no_stream_but_finished_call_sends_single_terminal_event(
    state: str, expected: str
) -> None:
    async for client in _client(create_app(make_settings()), FakeRedis(), make_call(state)):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    events = parse_sse(resp.text)
    assert [e[0] for e in events] == [expected]


async def test_unfinished_call_without_events_times_out_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcript_live, "MAX_DURATION_S", 0)
    monkeypatch.setattr(transcript_live, "BLOCK_MS", 1)
    redis = FakeRedis()
    async for client in _client(create_app(make_settings()), redis, make_call("beklemede")):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    assert [e[0] for e in parse_sse(resp.text)] == ["timeout"]
    assert redis.counters == {}  # bağlantı sayacı bırakıldı


async def test_unknown_call_is_404_and_takes_no_connection_slot() -> None:
    redis = FakeRedis()
    async for client in _client(create_app(make_settings()), redis, None):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    assert resp.status_code == 404
    assert redis.counters == {}


async def test_requires_service_key() -> None:
    async for client in _client(create_app(make_settings()), FakeRedis(), make_call("tamam")):
        no_key = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream")
        bad_key = await client.get(
            f"/api/v1/calls/{CALL_ID}/transcript/stream", headers={"X-Service-Key": "yanlis"}
        )

    assert no_key.status_code == 401 and bad_key.status_code == 401


async def test_owner_identity_gets_403_and_no_stream_data() -> None:
    key = secrets.token_urlsafe(32)
    user = str(uuid4())
    app = create_app(make_settings(user_signing_key=key, user_signature_required=True))
    redis = FakeRedis([seg(1, "rep", "ham metin"), {"type": "done"}])
    async for client in _client(app, redis, make_call("yaziya_cevriliyor")):
        resp = await client.get(
            f"/api/v1/calls/{CALL_ID}/transcript/stream",
            headers={
                **HEADERS,
                "X-User-Id": user,
                "X-User-Signature": sign_user_id(user, key, role="owner"),
                "X-User-Role": "owner",
            },
        )

    assert resp.status_code == 403
    assert "ham metin" not in resp.text
    assert redis.counters == {}


async def test_too_many_viewers_get_429() -> None:
    redis = FakeRedis([{"type": "done"}])
    redis.counters[transcript_live.conn_key(CALL_ID)] = transcript_live.MAX_CONNECTIONS_PER_CALL
    async for client in _client(create_app(make_settings()), redis, make_call("yaziya_cevriliyor")):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    # Sayaç artırılıp geri alındı; başka izleyicilerin sayacı bozulmadı.
    assert (
        redis.counters[transcript_live.conn_key(CALL_ID)]
        == transcript_live.MAX_CONNECTIONS_PER_CALL
    )


async def test_watching_is_audited_without_transcript_text() -> None:
    redis = FakeRedis([seg(1, "rep", "çok gizli ham metin"), {"type": "done"}])
    session = FakeSession(make_call("yaziya_cevriliyor"))
    async for client in _client(create_app(make_settings()), redis, None, session):
        resp = await client.get(f"/api/v1/calls/{CALL_ID}/transcript/stream", headers=HEADERS)

    assert resp.status_code == 200
    assert session.committed
    (event,) = session.added
    assert event.action == "canli_transkript_izlendi"
    assert event.target_type == "call" and str(event.target_id) == str(CALL_ID)
    assert "gizli" not in json.dumps(event.details or {}, ensure_ascii=False)
    assert redis.counters == {}  # akış bitince bağlantı bırakıldı

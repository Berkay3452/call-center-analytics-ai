"""Regresyon (#160): Celery görevleri her seferinde `asyncio.run` ile yeni döngü açar.

langchain_openai varsayılan httpx istemcisini süreç boyunca önbelleğe alır; bağlantı havuzu ilk
döngüye bağlı kaldığı için ikinci `asyncio.run`'da "Event loop is closed" alınıyordu.
Gerçek bir yerel HTTP sunucusuna (sahte OpenAI-uyumlu uç) iki ayrı döngüden istek atılır.
"""

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

import pytest

from app.agents.base import AnalysisContext, Segment
from app.agents.call_classifier import CallClassifierAgent
from app.llm.client import get_chat_model
from tests.conftest import make_settings

pytest.importorskip("langchain_openai")

_CLASSIFIER_REPLY = {
    "call_type": "servis",
    "confidence": 0.9,
    "reason": "Müşteri servis istedi.",
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = (
        "HTTP/1.1"  # keep-alive: havuzdaki bağlantı döngüler arası yeniden kullanılmak ister
    )

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(
            {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(_CLASSIFIER_REPLY)},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def fake_llm_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()
    server.server_close()


def _settings(url: str):
    return make_settings(
        llm_provider="openai_compatible",
        llm_base_url=url,
        llm_api_key="test-key",
        llm_fast_model="m",
        llm_smart_model="m",
        llm_max_retries=0,
        llm_requests_per_minute=0,
    )


def test_chat_model_survives_consecutive_asyncio_run(fake_llm_url: str) -> None:
    settings = _settings(fake_llm_url)

    async def call() -> str:
        model = get_chat_model("fast", settings)
        return str((await model.ainvoke("merhaba")).content)

    for _ in range(3):
        assert "servis" in asyncio.run(call())


def test_classifier_agent_survives_consecutive_asyncio_run(fake_llm_url: str) -> None:
    settings = _settings(fake_llm_url)
    ctx = AnalysisContext(
        call_id=uuid4(),
        segments=[
            Segment(
                idx=0, speaker="customer", start_ms=0, end_ms=1000, text_masked="Servis istiyorum."
            )
        ],
    )
    statuses = [
        asyncio.run(CallClassifierAgent(settings=settings).run(ctx)).status for _ in range(3)
    ]
    assert statuses == ["ok", "ok", "ok"]

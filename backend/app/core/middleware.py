"""İstek bağlamı ara katmanı.

Saf ASGI olarak yazıldı (BaseHTTPMiddleware değil); böylece RAG sohbetindeki
SSE akışlı yanıtlar tamponlanmadan geçer.

Her istek için:
- `X-Request-ID` başlığını okur ya da üretir, yanıta geri yazar,
- `request_id`'yi log bağlamına ekler,
- istek sonunda yöntem, yol, durum kodu ve süreyi loglar.
"""

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"
logger = structlog.get_logger("app.request")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.encode())
        # Dışarıdan gelen kimliği yalnızca makul uzunluktaysa kabul et (log zehirlemesine karşı).
        request_id = (
            incoming.decode("latin-1") if incoming and len(incoming) <= 64 else uuid.uuid4().hex
        )
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((REQUEST_ID_HEADER.encode(), request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()

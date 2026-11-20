"""API koruma ara katmanları (#271): hız sınırı, JSON gövde sınırı, güvenlik başlıkları.

Saf ASGI (SSE akışları tamponlanmaz). Sıra (dıştan içe): RequestContext → SecurityHeaders →
BodyLimit → RateLimit → CORS → uygulama. Böylece 413/429 yanıtları istek kimliği, güvenlik
başlıkları ve CORS başlıklarıyla döner.
"""

import re
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_json
from app.core.ratelimit import RateLimiter

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# LLM çağıran (maliyetli) uçlar: daha sıkı "asistan" sınırı da uygulanır.
ASSISTANT_PATHS = frozenset({"/chat/messages", "/chat/messages/stream", "/assistant/chat"})
BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _request_id(scope: Scope) -> str | None:
    state: dict[str, Any] = scope.get("state") or {}
    value = state.get("request_id")
    return str(value) if value else None


class RateLimitMiddleware:
    """IP + kimlik bazlı kayan pencere sınırı; aşımda 429 ve `Retry-After`.

    Anahtar: `genel:{ip}:{X-User-Id}` ve kimlikten bağımsız `ip-genel:{ip}` (asistan için
    `ip-asistan`). `X-User-Id` doğrulanmamış bir başlıktır (#266'ya kadar): yalnızca UUID
    biçimindeyse kimlik olarak kullanılır, yoksa `-` sayılır; her istekte yeni UUID gönderilerek
    kimlik kovası atlatılabilir, bu yüzden IP-only (daha yüksek tavanlı) kovalar da uygulanır.
    Asistan uçları ek olarak kendi (daha sıkı) kovasına sayılır.
    `/health*` ve CORS ön uçuşu (OPTIONS) sayılmaz.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: RateLimiter | None,
        prefix: str,
        general_per_min: int,
        assistant_per_min: int,
        ip_general_per_min: int,
        ip_assistant_per_min: int,
        window_s: int = 60,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.prefix = prefix.rstrip("/")
        self.general = general_per_min
        self.assistant = assistant_per_min
        self.ip_general = ip_general_per_min
        self.ip_assistant = ip_assistant_per_min
        self.window_s = window_s

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            scope["type"] != "http"
            or self.limiter is None
            or scope.get("method") == "OPTIONS"
            or not path.startswith(self.prefix + "/")
        ):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "bilinmeyen"
        raw_user = _header(scope, b"x-user-id") or ""
        user = raw_user.lower() if _UUID.fullmatch(raw_user) else "-"
        who = f"{ip}:{user}"

        # (kova, anahtar, sınır). IP-only kovalar kimlikten bağımsızdır: istemci her istekte yeni
        # UUID gönderse de IP tavanına takılır.
        checks = [("genel", f"genel:{who}", self.general)]
        is_assistant = scope.get("method") == "POST" and path[len(self.prefix) :] in ASSISTANT_PATHS
        if is_assistant:
            checks.append(("asistan", f"asistan:{who}", self.assistant))
        checks.append(("ip-genel", f"ip-genel:{ip}", self.ip_general))
        if is_assistant:
            checks.append(("ip-asistan", f"ip-asistan:{ip}", self.ip_assistant))
        for name, key, limit in checks:
            decision = await self.limiter.hit(key, limit, self.window_s)
            if not decision.allowed:
                response = error_json(
                    _request_id(scope),
                    429,
                    "rate_limited",
                    "Çok fazla istek gönderdiniz; lütfen biraz bekleyip yeniden deneyin.",
                    {"retry_after_s": decision.retry_after_s, "bucket": name},
                    {
                        "Retry-After": str(decision.retry_after_s),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """JSON (multipart olmayan) istek gövdesi üst sınırı; aşımda 413.

    Ses yüklemesi (multipart) kendi sınırına (`AUDIO_MAX_MB`, 413) sahiptir ve burada sayılmaz.
    `Content-Length` varsa gövde okunmadan reddedilir; yoksa (chunked) okunan bayt sayılır ve
    sınır aşılınca gövde kesilir ve uygulamanın yanıtı standart 413 gövdesiyle değiştirilir.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        content_type = (_header(scope, b"content-type") or "").lower()
        if content_type.startswith("multipart/"):
            await self.app(scope, receive, send)
            return

        declared = _header(scope, b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            response = error_json(
                _request_id(scope),
                413,
                "payload_too_large",
                f"İstek gövdesi en fazla {self.max_bytes // 1024} KB olabilir.",
                {"max_bytes": self.max_bytes},
            )
            await response(scope, receive, send)
            return

        received = 0
        overflow = False
        replied = False

        async def limited_receive() -> Message:
            nonlocal received, overflow
            if overflow:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Uç nokta gövdeyi okurken 400'e çevirebilir; yanıt aşağıda 413 ile değişir.
                    overflow = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal replied
            if not overflow:
                await send(message)
                return
            if not replied:
                replied = True
                response = error_json(
                    _request_id(scope),
                    413,
                    "payload_too_large",
                    f"İstek gövdesi en fazla {self.max_bytes // 1024} KB olabilir.",
                    {"max_bytes": self.max_bytes},
                )
                await response(scope, receive, send)

        await self.app(scope, limited_receive, guarded_send)


class SecurityHeadersMiddleware:
    """API yanıtlarına tarayıcı güvenlik başlıkları (#271). HSTS yalnızca canlıda (TLS)."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.extra: list[tuple[bytes, bytes]] = [
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-frame-options", b"DENY"),
            # Kişisel veri içeren yanıtlar tarayıcı/ara sunucu önbelleğine yazılmasın.
            (b"cache-control", b"no-store"),
        ]
        if hsts:
            self.extra.append(
                (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {k.lower() for k, _ in headers}
                headers.extend(h for h in self.extra if h[0] not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

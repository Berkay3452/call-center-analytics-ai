"""Sahte OpenAI-uyumlu LLM sunucusu: duman testinde gerçek LLM yerine (#157).

Dört analiz agent'ının istediği şemaya (prompt'taki JSON şemasının başlığı) uyan sabit, geçerli bir
JSON döner; böylece yükleme → STT → analiz hattı kota ve ağ olmadan uçtan uca denenir.

    python -m scripts.fake_llm --port 9101

Kullanım: `LLM_PROVIDER=openai_compatible LLM_BASE_URL=http://127.0.0.1:9101/v1 LLM_API_KEY=sahte
LLM_FAST_MODEL=sahte LLM_SMART_MODEL=sahte`. Üretimde kullanılmaz.
"""

import argparse
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SCHEMA_TITLE = re.compile(
    r'"title":\s*"(CallClassification|CrmExtraction|SalesAnalysis|CallSummary)"'
)

CANNED: dict[str, dict[str, Any]] = {
    "CallClassification": {
        "call_type": "servis",
        "confidence": 0.9,
        "reason": "Sahte LLM: müşteri servis talebi iletiyor.",
    },
    "CrmExtraction": {"urgency": "normal", "evidence": {}},
    "SalesAnalysis": {
        "outcome": "beklemede",
        "loss_reason": None,
        "evidence": None,
        "confidence": 0.7,
    },
    "CallSummary": {
        "summary": "Müşteri bir servis talebi iletti.",
        "key_points": ["Servis talebi"],
    },
}


def canned_reply(request: dict[str, Any]) -> str:
    """İstekteki mesajlardan hangi agent'ın sorduğunu bulup sabit JSON'unu döner."""
    text = " ".join(str(m.get("content", "")) for m in request.get("messages", []))
    match = SCHEMA_TITLE.search(text)
    return json.dumps(CANNED[match.group(1)] if match else {}, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        pass

    def do_GET(self) -> None:
        self._send(200, {"status": "ok"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        completion = {
            "id": "sahte", "object": "chat.completion", "created": 0,
            "model": request.get("model", "sahte"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": canned_reply(request)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }  # fmt: skip
        self._send(200, completion)

    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Sunucuyu arka plan iş parçacığında başlatır (testler için); `server_address[1]` portudur."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9101)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Sahte LLM {args.host}:{args.port} üzerinde dinliyor.", file=sys.stderr, flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

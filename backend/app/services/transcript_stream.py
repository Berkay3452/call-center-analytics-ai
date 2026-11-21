"""Canlı transkript yayını (#323): STT segmentlerini Redis Stream'ine yazar.

İşçi (Celery, senkron iş parçacığı) yazar; API (#324) okur. Anahtar `transcript:{call_id}`.
Olay türleri: `segment` (konuşma parçası), `turn` (konuşmacı ayrımı sonrası nihai cümle),
`done` (STT bitti), `error` (STT başarısız).

Güvenlik/dayanıklılık:
- Akıştaki metin **ham** transkripttir (yalnızca yönetici bağlamındaki uç okur); metin günlüğe ve
  anahtar adına yazılmaz, hata iletisi yerine sabit kod yayınlanır.
- Yayın başarısızlığı STT'yi **asla** düşürmez: hata bir kez uyarı olarak günlüğe yazılır, sonra
  bu çağrı için yayın kapatılır (her segmentte tekrar bağlanma denemesi yok).
- Akış sınırlıdır: en çok `maxlen` olay, `ttl_s` saniye sonra silinir.
"""

import contextlib
import threading
from typing import Any, Literal

import structlog
from redis import Redis

from app.core.config import Settings
from app.stt.base import SttSegment

log = structlog.get_logger(__name__)

EventType = Literal["segment", "turn", "done", "error"]
ERROR_CODE = "stt_failed"  # sabit kod; ham hata metni yayınlanmaz


def stream_key(call_id: object) -> str:
    return f"transcript:{call_id}"


class TranscriptPublisher:
    """Tek çağrının segmentlerini yayınlar. İş parçacığı güvenlidir (segmentler işçi iş
    parçacığından, `done`/`error` olay döngüsünden gelir)."""

    def __init__(
        self,
        client: Redis | None,
        call_id: object,
        *,
        maxlen: int = 5000,
        ttl_s: int = 3600,
    ) -> None:
        self._client = client
        self._key = stream_key(call_id)
        self._maxlen = maxlen
        self._ttl_s = ttl_s
        self._seq = 0
        self._lock = threading.Lock()
        self._broken = client is None

    @classmethod
    def from_settings(cls, settings: Settings, call_id: object) -> "TranscriptPublisher":
        if not settings.live_transcript_enabled:
            return cls(None, call_id)
        try:
            client = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
        except Exception:
            log.warning("transcript_stream.client_failed")
            return cls(None, call_id)
        return cls(
            client,
            call_id,
            maxlen=settings.live_transcript_maxlen,
            ttl_s=settings.live_transcript_ttl_s,
        )

    @property
    def enabled(self) -> bool:
        return not self._broken

    def _add(self, fields: dict[str, Any]) -> None:
        if self._broken or self._client is None:
            return
        try:
            self._client.xadd(self._key, fields, maxlen=self._maxlen, approximate=True)  # type: ignore[arg-type]
            self._client.expire(self._key, self._ttl_s)
        except Exception as exc:  # Redis kapalı/yavaş: analiz sürer
            self._broken = True
            log.warning("transcript_stream.publish_failed", error=type(exc).__name__)

    def publish_segment(self, segment: SttSegment) -> None:
        """Segment hazır olunca çağrılır; asla hata fırlatmaz."""
        with self._lock:
            self._seq += 1
            self._add(
                {
                    "type": "segment",
                    "seq": self._seq,
                    "speaker": segment.speaker or "unknown",
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text": segment.text.strip(),
                }
            )

    def publish_turns(self, segments: list[SttSegment]) -> None:
        """Konuşmacı ayrımı bitince nihai, etiketli cümleleri yayınlar (pop-up canlı metni
        bunlarla değiştirir). Asla hata fırlatmaz."""
        with self._lock:
            for seg in sorted(segments, key=lambda x: (x.start_ms, x.end_ms)):
                if not seg.text.strip():
                    continue
                self._seq += 1
                self._add(
                    {
                        "type": "turn",
                        "seq": self._seq,
                        "speaker": seg.speaker or "unknown",
                        "start_ms": seg.start_ms,
                        "end_ms": seg.end_ms,
                        "text": seg.text.strip(),
                    }
                )

    def publish_done(self) -> None:
        with self._lock:
            self._add({"type": "done", "seq": self._seq + 1})

    def publish_error(self) -> None:
        with self._lock:
            self._add({"type": "error", "seq": self._seq + 1, "code": ERROR_CODE})

    def close(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()

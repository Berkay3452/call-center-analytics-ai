"""Düz metin transkriptlerin konuşma turlarına ayrılması.

Hem `POST /calls` (metinle gelen çağrı) hem STT'nin stub sağlayıcısı kullanır.
"""

import re
from collections.abc import Sequence

from app.agents.base import Speaker
from app.schemas.api import SegmentIn

SPEAKER_PREFIXES: dict[str, Speaker] = {
    "müşteri": "customer",
    "musteri": "customer",
    "customer": "customer",
    "temsilci": "rep",
    "rep": "rep",
    "agent": "rep",
}
_LINE = re.compile(r"^\s*([^\W\d_]+)\s*:\s*(.*)$")
# Konuşma süresi bilinmeyen segmentler için tahmini hız (karakter başına ms).
MS_PER_CHAR = 65


def parse_transcript(text: str) -> list[SegmentIn]:
    """Düz metni konuşmacı satırlarına böler ("Müşteri: ..." / "Temsilci: ...").

    Konuşmacı etiketi olmayan satır öncekine eklenir; hiç etiket yoksa tek müşteri segmenti olur.
    """
    segments: list[SegmentIn] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LINE.match(line)
        speaker = SPEAKER_PREFIXES.get(match.group(1).lower()) if match else None
        if match and speaker:
            body = match.group(2).strip()
            if body:
                segments.append(SegmentIn(speaker=speaker, text=body))
        elif segments:
            last = segments[-1]
            segments[-1] = last.model_copy(update={"text": f"{last.text} {line}"})
        else:
            segments.append(SegmentIn(speaker="customer", text=line))
    return segments


def with_timings(segments: Sequence[SegmentIn]) -> list[tuple[SegmentIn, int, int]]:
    """Zaman bilgisi olmayan segmentlere tahmini süre verir (sıralı, örtüşmeyen)."""
    out: list[tuple[SegmentIn, int, int]] = []
    cursor = 0
    for seg in segments:
        start = seg.start_ms if seg.start_ms is not None else cursor
        estimated = start + max(1000, len(seg.text) * MS_PER_CHAR)
        end = max(seg.end_ms if seg.end_ms is not None else estimated, start)
        out.append((seg, start, end))
        cursor = end
    return out

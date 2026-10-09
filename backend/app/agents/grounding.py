"""Alıntı doğrulama: agent'ın "konuşmadan alıntı" dediği metin gerçekten konuşmada geçiyor mu?

LLM'ler bazen alıntıyı kendi cümlesiyle yeniden yazar veya hiç geçmeyen bir söz uydurur.
Arayüzde "müşteri bunu söyledi" diye gösterilecek metnin konuşmada gerçekten geçmesi gerekir.

Karşılaştırma büyük/küçük harfe, noktalamaya, fazla boşluğa ve Türkçe karakter farklarına
(ı/i, ş/s, ğ/g, ü/u, ö/o, ç/c) duyarsızdır; kelimelerin kendisi ve sırası aynı olmalıdır.
"""

import re
import unicodedata

from app.agents.base import Segment

_NON_WORD = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    """Karşılaştırma için sadeleştirir: "Tuzla Marina'da!" → "tuzla marina da"."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    ascii_like = "".join(ch for ch in folded if not unicodedata.combining(ch)).replace("ı", "i")
    return _NON_WORD.sub(" ", ascii_like).strip()


def transcript_text(segments: list[Segment]) -> str:
    """Tüm konuşmanın sadeleştirilmiş hali (başında ve sonunda boşlukla)."""
    return f" {normalize(' '.join(s.text_masked for s in segments))} "


def is_grounded(quote: str, normalized_transcript: str) -> bool:
    """Alıntı konuşmada (kelime sınırlarına uyarak) geçiyor mu?"""
    needle = normalize(quote)
    return bool(needle) and f" {needle} " in normalized_transcript

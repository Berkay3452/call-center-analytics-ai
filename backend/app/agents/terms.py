"""Türkçe teknik terim ve konum düzeltmeleri (#84).

LLM çıktısındaki sık yazım hatalarını (ör. "generatör") ve aynı yerin farklı yazımlarını
("Kalamış" / "Kalamış Marina") deterministik olarak düzeltir. LLM'e güvenmek yerine kodla
yapılır: sonuç tekrarlanabilir ve testlenebilir.
"""

import re
from collections.abc import Callable

from app.agents.grounding import normalize

# (yanlış yazım öneki, doğru yazım): ekler korunur ("generatörünün" → "jeneratörünün").
_TERM_FIXES: tuple[tuple[str, str], ...] = (
    ("generatör", "jeneratör"),
    ("generator", "jeneratör"),
    ("empeller", "impeller"),
    ("impelör", "impeller"),
    ("sentine", "sintine"),
)
_TERM_PATTERNS = [
    (re.compile(rf"\b{re.escape(wrong)}", re.IGNORECASE), right) for wrong, right in _TERM_FIXES
]


def _replacer(right: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return right.capitalize() if match.group(0)[:1].isupper() else right

    return replace


def fix_terms(text: str) -> str:
    """Bilinen yazım hatalarını düzeltir; büyük harfle başlayan kelimenin harf biçimini korur."""
    for pattern, right in _TERM_PATTERNS:
        text = pattern.sub(_replacer(right), text)
    return text


# Yer adlarını karşılaştırırken anlam taşımayan kelimeler.
_GENERIC_PLACE_WORDS = frozenset(
    {"marina", "marin", "d", "tersane", "tersaneler", "tersaneleri", "yat", "limani", "liman"}
)


def _place_tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in normalize(name).split() if t not in _GENERIC_PLACE_WORDS)


def same_place(a: str, b: str) -> bool:
    """İki yer adı aynı yeri anlatıyor mu? ("Kalamış" ile "Kalamış Marina" → True)."""
    ta, tb = _place_tokens(a), _place_tokens(b)
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta

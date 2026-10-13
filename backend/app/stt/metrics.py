"""STT karşılaştırma ölçütleri: kelime ve karakter hata oranı (WER/CER).

Türkçe için normalleştirme: büyük/küçük harf (İ→i, I→ı), noktalama ve maske belirteçleri
(`[İSİM]` gibi; referans metinde maskeli olan, seste ise gerçek ad olan yerler) çıkarılır.
"""

import re

_MASK = re.compile(r"\[[^\]]*\]")
_NON_WORD = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    text = _MASK.sub(" ", text)
    text = text.replace("I", "ı").replace("İ", "i").lower()
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.split())


def _edit_distance(ref: list[str], hyp: list[str]) -> int:
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Kelime hata oranı: (ekleme + silme + değiştirme) / referans kelime sayısı."""
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    """Karakter hata oranı (boşluksuz); Türkçenin eklemeli yapısında WER'i tamamlar."""
    ref = list(normalize(reference).replace(" ", ""))
    hyp = list(normalize(hypothesis).replace(" ", ""))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)

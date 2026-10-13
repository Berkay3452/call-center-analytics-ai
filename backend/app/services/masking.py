"""Kişisel verilerin maskelenmesi (KVKK): LLM ve arama yalnızca maskeli metni görür.

Kural tabanlıdır ve bilinçli olarak basittir: telefon, e-posta, IBAN, T.C. kimlik no ve çağrı
bilgisinden bilinen ad/soyadlar maskelenir. Serbest metindeki tanınmayan adlar yakalanamaz;
sentetik veride adlar zaten `[İSİM]` olarak gelir. Gerçek veriye geçilirse ad tanıma (NER)
eklenmelidir.

Belirteçler (`[TELEFON]` gibi) özetleyici agent'ın kontrol ettiği biçimdedir
(bkz. `app/agents/summarizer.py`).
"""

import re
from collections.abc import Iterable

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_IBAN = re.compile(r"\bTR\d{2}(?:[\s]?\d{4}){5}[\s]?\d{2}\b", re.IGNORECASE)
_TC_ID = re.compile(r"(?<!\d)\d{11}(?!\d)")
# En az 10 rakam içeren, boşluk/tire/parantez ile bölünebilen numaralar (+90 532 123 45 67 vb.).
_PHONE = re.compile(r"(?<!\w)\+?\d(?:[\s\-()]*\d){9,}(?!\w)")


def mask_text(text: str, names: Iterable[str | None] = ()) -> str:
    """Metindeki kişisel verileri belirteçle değiştirir. `names`: bilinen ad ve soyadlar."""
    masked = _EMAIL.sub("[EPOSTA]", text)
    masked = _IBAN.sub("[IBAN]", masked)
    masked = _TC_ID.sub("[KİMLİK]", masked)
    masked = _PHONE.sub("[TELEFON]", masked)
    for name in names:
        if not name or not name.strip():
            continue
        # Tam ad ve ayrı ayrı her kelime (kısa kelimeler hariç) harf büyüklüğüne bakmadan.
        parts = [name.strip(), *[p for p in name.split() if len(p) >= 3]]
        for part in sorted(set(parts), key=len, reverse=True):
            masked = re.sub(
                rf"(?<!\w){re.escape(part)}(?!\w)", "[İSİM]", masked, flags=re.IGNORECASE
            )
    return masked

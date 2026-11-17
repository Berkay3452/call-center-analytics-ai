"""Kişisel verilerin maskelenmesi (KVKK): LLM ve arama yalnızca maskeli metni görür.

Kural tabanlıdır ve bilinçli olarak basittir; NER yoktur. Kapsam:

- yapısal veriler: e-posta, IBAN, T.C. kimlik no, telefon, banka/kredi kartı (Luhn doğrulamalı),
  vergi no, pasaport/ehliyet no, araç ve tekne plakası/tescil no
- adres kalıpları: "... Mahallesi", "... Sokak/Cadde/Bulvarı" ve ardından gelen No/Daire/Kat
- ad kalıpları: "Ben X", "Adım X", "X Bey/Hanım" (bilinen listede olmasa da)
- çağrı bilgisinden bilinen ad/soyadlar (harf büyüklüğüne bakmadan)

Sınır: Kalıba uymayan serbest ad ("Mehmet'e söyleyin"), küçük harfli STT çıktısındaki adresler
ve yazıyla söylenen numaralar yakalanamaz. Ölçüm ve sayılar: `docs/maskeleme_olcum.md`.

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
# 13-19 rakamlık, boşluk/tireyle bölünebilen dizi; yalnızca Luhn'u geçerse kart sayılır.
_CARD = re.compile(r"(?<![\d\w])\d(?:[ \-]?\d){12,18}(?![\d\w])")
# "vergi no 1234567890": yalnızca bağlam varsa (10 haneli her sayı vergi no değildir).
_TAX_ID = re.compile(r"((?i:vergi\s+(?:kimlik\s+)?(?:no|numara\w*)|vkn)\s*[:\-]?\s*)(\d{10})(?!\d)")
# "pasaport no U12345678", "ehliyet numaram 12345678": anahtar sözcük + en az bir rakamlı kimlik.
_DOC_CONTEXT = re.compile(
    r"((?i:pasaport|ehliyet|sürücü\s+belge\w*)\w*(?:\s+(?:seri\s+)?(?i:no|numara\w*))?\s*[:\-]?\s*)"
    r"((?=[A-Za-z0-9]*\d)[A-Za-z0-9]{6,12})(?!\w)"
)
_PASSPORT_BARE = re.compile(r"(?<![\w\[])[A-Z]\d{8}(?!\w)")

# Araç plakası: il kodu (01-81) + 1-3 harf + 2-4 rakam. Büyük harf zorunlu; birim kısaltmaları
# ("40 HP 2500 devir") plaka sayılmaz.
_PLATE = re.compile(r"(?<![\w\[])(?:0[1-9]|[1-7]\d|8[01])\s?([A-ZÇĞİÖŞÜ]{1,3})\s?\d{2,4}(?![\w\]])")
_PLATE_NOT_LETTERS = {"TL", "HP", "KW", "PS", "CC", "KG", "GB", "MB", "DK", "SN", "TB", "AH", "KV"}
# "tekne tescil no BDR-1234", "plaka: TR-12345": anahtar sözcük + rakamlı büyük harfli kod.
_BOAT_REG = re.compile(
    r"((?i:tescil|sicil|bağlama\s+kütüğ|plaka)\w*(?:\s+(?i:no|numara\w*))?\s*[:\-]?\s*)"
    r"((?=[A-ZÇĞİÖŞÜ0-9\-/]*\d)[A-ZÇĞİÖŞÜ0-9][A-ZÇĞİÖŞÜ0-9\-/]{3,12})(?![\w\]])"
)

_WORD = r"[A-ZÇĞİÖŞÜ][a-zçğıöşüâîû]+"
# Adres: "Cumhuriyet Mahallesi", "Atatürk Cad.", "1234. Sokak"; ardından No/Daire/Kat birleştirilir.
_ADDRESS_UNIT = re.compile(
    rf"(?<![\w\[])(?:(?:{_WORD}|\d{{1,4}}\.)\s+){{1,3}}"
    r"(?i:mahallesi|mahalle|mah\.|mah|sokağı|sokak|sk\.|sk|caddesi|cadde|cad\.|cad|cd\.|cd"
    r"|bulvarı|bulvar|apartmanı|sitesi)(?!\w)"
)
_ADDRESS_TAIL = re.compile(
    r"\[ADRES\](?:[\s,]*(?:\[ADRES\]"
    r"|(?i:no|numara|daire|kat|blok)\s*[:.]?\s*\d+[A-Za-z]?(?:/\d+)?"
    r"|\d{1,4}(?:/\d{1,3})?(?!\d)"
    r"|(?:[A-Z]\s+)?(?i:blok)(?!\w)))+"
)

# Ad kalıpları: "Ben X", "Adım X", "X Bey/Hanım". Kalıp dışındaki adlar yakalanamaz.
_NAME_INTRO = re.compile(
    rf"(?<![\w\[])((?i:ben|adım|ismim|isim|soyadım|sahibi)[\s:,\-]+)"
    rf"((?:{_WORD})(?:\s+(?:{_WORD})){{0,2}})"
)
_NAME_TITLE = re.compile(
    rf"(?<![\w\[])((?:{_WORD})(?:\s+(?:{_WORD})){{0,2}})(\s+(?:Bey|Hanım|Hanim)(?!\w))"
)
# Ad sayılmayan sözcükler: cümle başı sözcükleri, unvanlar, kurum ve yer sözcükleri.
_NOT_NAME = {
    s.casefold()
    for s in [
        "Merhaba",
        "Selam",
        "Evet",
        "Hayır",
        "Tamam",
        "Peki",
        "Sayın",
        "Efendim",
        "İyi",
        "Günaydın",
        "Teşekkürler",
        "Tabii",
        "Tabi",
        "Usta",
        "Kaptan",
        "Müdür",
        "Doktor",
        "Mühendis",
        "Hoca",
        "Hocam",
        "Abi",
        "Abla",
        "Miço",
        "Marina",
        "Marinası",
        "Liman",
        "Limanı",
        "Yat",
        "Kulüp",
        "Kulübü",
        "Servis",
        "Teknik",
        "Şirket",
        "Firma",
        "Adım",
        "Ben",
        "Biz",
        "Bir",
        "Bu",
        "Şu",
        "O",
        "Şimdi",
        "Sonra",
        "Önce",
        "Ama",
        "Fakat",
        "Çünkü",
        "Yani",
        "Ayrıca",
        "Lütfen",
        "Rica",
        "Hanım",
        "Bey",
        "Bay",
        "Bayan",
        "Müşteri",
        "Yetkili",
        "Sahibi",
        "Motor",
        "Tekne",
        "Jeanneau",
        "Beneteau",
        "Bavaria",
        "Volvo",
        "Yanmar",
    ]
}
# "Ben Tuzla Marina'dan" gibi yer bildiren eklerden önceki sözcükler ad değildir.
_PLACE_SUFFIX = re.compile(r"['’](?:da|de|ta|te|dan|den|tan|ten|ya|ye)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def _mask_cards(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[KART]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group(0)

    return _CARD.sub(repl, text)


def _mask_plates(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        return m.group(0) if m.group(1) in _PLATE_NOT_LETTERS else "[PLAKA]"

    return _PLATE.sub(repl, text)


def _split_name(group: str) -> tuple[str, str, str] | None:
    """`group`u (önce, ad, sonra) olarak böler; baştaki/sondaki ad olmayan sözcükler dışarıda kalır.

    Ad kalmazsa None döner.
    """
    words = group.split()
    start = 0
    while start < len(words) and words[start].casefold() in _NOT_NAME:
        start += 1
    end = start
    while end < len(words) and words[end].casefold() not in _NOT_NAME:
        end += 1
    if start == end:
        return None
    return (
        " ".join(words[:start]) + (" " if start else ""),
        " ".join(words[start:end]),
        (" " if end < len(words) else "") + " ".join(words[end:]),
    )


def _mask_name_patterns(text: str) -> str:
    def repl_intro(m: re.Match[str]) -> str:
        parts = _split_name(m.group(2))
        if parts is None or _PLACE_SUFFIX.match(text, m.end()):
            return m.group(0)
        before, _, after = parts
        return f"{m.group(1)}{before}[İSİM]{after}"

    def repl_title(m: re.Match[str]) -> str:
        parts = _split_name(m.group(1))
        if parts is None:
            return m.group(0)
        before, _, after = parts
        return f"{before}[İSİM]{after}{m.group(2)}"

    text = _NAME_INTRO.sub(repl_intro, text)
    return _NAME_TITLE.sub(repl_title, text)


def mask_text(text: str, names: Iterable[str | None] = ()) -> str:
    """Metindeki kişisel verileri belirteçle değiştirir. `names`: bilinen ad ve soyadlar."""
    masked = _EMAIL.sub("[EPOSTA]", text)
    masked = _IBAN.sub("[IBAN]", masked)
    masked = _mask_cards(masked)
    masked = _TAX_ID.sub(r"\1[VERGİ_NO]", masked)
    masked = _DOC_CONTEXT.sub(r"\1[BELGE_NO]", masked)
    masked = _PASSPORT_BARE.sub("[BELGE_NO]", masked)
    masked = _TC_ID.sub("[KİMLİK]", masked)
    masked = _PHONE.sub("[TELEFON]", masked)
    masked = _mask_plates(masked)
    masked = _BOAT_REG.sub(r"\1[PLAKA]", masked)
    masked = _ADDRESS_UNIT.sub("[ADRES]", masked)
    masked = _ADDRESS_TAIL.sub("[ADRES]", masked)
    masked = _mask_name_patterns(masked)
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

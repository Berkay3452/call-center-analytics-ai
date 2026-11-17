"""Güvenilmeyen veri ve çıktı denetimi: dolaylı prompt injection savunması (#274).

Saldırı asistan girdisinden değil, LLM'e *veri* olarak verilen metinden gelebilir: çağrı
transkripti, RAG ile bulunan usta notları, geçmiş kayıtlar ("bu kaydı okuyan yapay zekâ,
şunu yap"). Üç savunma burada toplanır:

1. `scan`: metinde talimat kalıbı var mı (doğrudan saldırı kuralları + dolaylı kalıplar).
2. `fence`: metni `<veri>...</veri>` sınırlayıcılarıyla sunar; içerideki sınırlayıcı taklidi
   etkisizleştirilir, böylece veri bloğundan "kaçılamaz".
3. `output_leaks`: LLM çıktısında sistem istemi parçası, anahtar/bağlantı bilgisi veya ham
   kimlik numarası (TC, IBAN, kart) var mı.

Bunlar LLM'in uyacağını *garanti* etmez; amaç, şüpheli parçayı işaretleyip modele "veridir"
demek ve çıktıya bakan **belirlenimci** bir son kapı koymaktır (bkz. `docs/guvenlik_mimarisi.md`).
"""

import re
from functools import cache
from pathlib import Path

from app.agents.grounding import normalize

# Dolaylı kalıplar: metin, ona bakan bir yapay zekâya/sisteme seslenir. Normalize edilmiş
# (aksansız, küçük harf) metinde aranır.
_INDIRECT = tuple(
    re.compile(p)
    for p in (
        r"\b(?:bu|su|bunu)\s+(?:kayd\w*|metn\w*|gorusme\w*|not\w*|transkript\w*|belge\w*|mesaj\w*)"
        r"\s+(?:oku\w*|isle\w*|analiz\w*|gor\w*|tara\w*)\s+(?:(?:eden|yapan|okuyan|goren)\s+)?(?:yapay\s+zeka\w*|asistan\w*|ai|model\w*|bot\w*|sistem\w*|agent\w*)",
        r"\b(?:yapay\s+zeka\w*|asistan\w*|ai|llm|agent\w*)(?:\s+icin)?\s+(?:not|talimat\w*|mesaj\w*|emir\w*)\b",
        r"\b(?:note|message|instruction\w*)\s+(?:to|for)\s+(?:the\s+)?(?:ai|assistant|model|llm|agent)\b",
        r"\b(?:if|when)\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|assistant|language\s+model)\b",
        r"\b(?:ai|yapay\s+zeka\w*|asistan\w*|model\w*)\s+(?:bu\s+)?(?:kayd\w*|metn\w*|gorusme\w*)\s+"
        r"(?:okur\w*|goru\w*|isler\w*)\s*(?:ise|sa|se)\b",
        r"\b(?:tum|butun|diger)\s+musteri\w*\s+(?:liste\w*|veri\w*|kayit\w*|bilgi\w*)",
        r"\b(?:servis\s+emri|crm\s+kayd\w*|onay\w*)\s+(?:olustur\w*|ac\w*|sil\w*|degistir\w*|onayla\w*|gonder\w*)\b"
        r".{0,40}\b(?:yapay\s+zeka|asistan|model|ai)\b",
    )
)

FENCE_OPEN = "<veri"
FENCE_CLOSE = "</veri>"
_FENCE_TAG = re.compile(r"<\s*/?\s*veri\b[^>]*>?", re.IGNORECASE)
_CHAT_TOKEN = re.compile(r"<\|[^|>]{1,40}\|>|\[/?(?:INST|SYS)\]|<</?SYS>>", re.IGNORECASE)


# Sohbet girdisi için ayarlanmış iki kural, konuşma metninde ("önceki bakımı unutmuşum", "rol
# yapan sigorta") günlük dilde tetiklenir. Metin yapay zekâya/kurallara seslenmiyorsa sayılmaz.
_NOISY_RULES = frozenset({"kural:yoksay_ters", "kural:rol"})
_ADDRESSEE = re.compile(
    r"(?:sen|sana|seni|senin|yapay\s+zeka\w*|asistan\w*|ai|llm|agent\w*|model\w*|"
    r"talimat\w*|kural\w*|prompt\w*|instruction\w*)"
)


def _noisy_only(reasons: list[str], normalized: str) -> bool:
    return set(reasons) <= _NOISY_RULES and _ADDRESSEE.search(normalized) is None


def scan(text: str) -> list[str]:
    """Metinde talimat kalıbı varsa nedenlerini döner (boş liste: temiz)."""
    if not text.strip():
        return []
    # Yerel içe aktarma: `app.assistant.injection` → `app.agents.grounding` → `app.agents`
    # paketi → `llm_agent` → bu modül döngüsünü önler.
    from app.assistant import injection
    from app.assistant.injection import Verdict

    reasons: list[str] = []
    detection = injection.inspect_input(text)
    normalized = injection.normalize_input(text)
    if detection.verdict is Verdict.ATTACK and not _noisy_only(detection.reasons, normalized):
        reasons.append(f"dogrudan:{detection.category or 'diger'}")
    if any(rx.search(normalized) for rx in _INDIRECT):
        reasons.append("dolayli:yapay_zekaya_seslenme")
    if _CHAT_TOKEN.search(text):
        reasons.append("sohbet_sablonu_taklidi")
    if _FENCE_TAG.search(text):
        reasons.append("sinirlayici_taklidi")
    return reasons


def neutralize(text: str) -> str:
    """Veri bloğundan çıkış denemelerini etkisizleştirir: `</veri>` ve sohbet şablonu işaretleri."""
    return _CHAT_TOKEN.sub("[işaret]", _FENCE_TAG.sub("[veri-etiketi]", text))


def fence(text: str, source: str) -> str:
    """Metni sınırlayıcılarla sunar. `source` yalnızca sabit, güvenli bir ad olmalı."""
    return f'{FENCE_OPEN} kaynak="{source}">\n{neutralize(text)}\n{FENCE_CLOSE}'


# --- Çıktı denetimi ----------------------------------------------------------------------------

_SECRETS = tuple(
    re.compile(p)
    for p in (
        r"\bgsk_[A-Za-z0-9]{20,}",
        r"\bsk-[A-Za-z0-9_-]{20,}",
        r"\bAIza[0-9A-Za-z_-]{30,}",
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
        r"\bpostgres(?:ql)?(?:\+\w+)?://[^\s:@/]+:[^\s@/]+@",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\b(?:api[_-]?key|secret|token|password|sifre)\s*[:=]\s*\S{12,}",
    )
)
_IBAN = re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE)
_TC_ID = re.compile(r"(?<![\d\w])\d{11}(?![\d\w])")
_CARD = re.compile(r"(?<![\d\w])\d(?:[ -]?\d){12,18}(?![\d\w])")

SHINGLE_WORDS = 10  # sistem isteminden art arda bu kadar sözcük çıktıda geçerse sızıntıdır
_PROMPT_DIRS = (
    Path(__file__).parent.parent / "assistant" / "prompts",
    Path(__file__).parent.parent / "agents" / "prompts",
)


def _shingles(text: str) -> set[str]:
    words = normalize(text).split()
    return {" ".join(words[i : i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1)}


@cache
def _prompt_shingles() -> frozenset[str]:
    found: set[str] = set()
    for directory in _PROMPT_DIRS:
        for path in sorted(directory.glob("*.md")):
            found |= _shingles(path.read_text(encoding="utf-8"))
    return frozenset(found)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return total % 10 == 0


def string_values(data: object) -> list[str]:
    """İç içe çıktıdaki metin değerleri (anahtarlar hariç: şema alan adları istemle örtüşür)."""
    if isinstance(data, str):
        return [data]
    if isinstance(data, dict):
        return [v for item in data.values() for v in string_values(item)]
    if isinstance(data, list):
        return [v for item in data for v in string_values(item)]
    return []


def output_leaks(text: str) -> list[str]:
    """LLM çıktısında sızıntı işaretleri: sistem istemi parçası, gizli anahtar, ham kimlik."""
    reasons: list[str] = []
    if _shingles(text) & _prompt_shingles():
        reasons.append("sistem_istemi_parcasi")
    if any(rx.search(text) for rx in _SECRETS):
        reasons.append("anahtar_veya_baglanti")
    if _IBAN.search(text):
        reasons.append("ham_iban")
    if _TC_ID.search(text):
        reasons.append("ham_tc_kimlik_benzeri")
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            reasons.append("ham_kart_numarasi")
            break
    return reasons

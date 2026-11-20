"""STT karşılaştırma ölçütleri: kelime ve karakter hata oranı (WER/CER).

Türkçe için normalleştirme: büyük/küçük harf (İ→i, I→ı), noktalama ve maske belirteçleri
(`[İSİM]` gibi; referans metinde maskeli olan, seste ise gerçek ad olan yerler) çıkarılır.
"""

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

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


# --- Alan terimi doğruluğu (#328) -------------------------------------------------------------
# Genel WER, "ve", "bir" gibi sözcüklerle seyrelir; asıl iş değerini taşıyan marka, parça, yer,
# gün ve sayı sözcüklerinin doğru yazılıp yazılmadığı ayrıca ölçülür.

TERMS_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "data" / "stt_referans" / "terimler.json"
)
_EXACT = "="  # kökün önündeki işaret: yalnız tam eşleşir ("=on" için "onu" sayılmaz)
_DIGITS = re.compile(r"^\d+$")
_ONES = ("", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
_TENS = ("", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan")


def number_to_words(n: int) -> str:
    """0-999999 arası sayının Türkçe yazılışı ("1300" -> "bin üç yüz"; "bir yüz/bin" denmez)."""
    if n == 0:
        return "sıfır"
    parts: list[str] = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        parts += ([] if thousands == 1 else _below_thousand(thousands)) + ["bin"]
    return " ".join(parts + _below_thousand(rest))


def _below_thousand(n: int) -> list[str]:
    hundreds, rest = divmod(n, 100)
    words: list[str] = []
    if hundreds:
        words += ([] if hundreds == 1 else [_ONES[hundreds]]) + ["yüz"]
    tens, ones = divmod(rest, 10)
    return [w for w in (*words, _TENS[tens], _ONES[ones]) if w]


def digits_to_words(text: str) -> str:
    """Normalleştirilmiş metindeki rakam dizilerini sözcüğe çevirir (6+ hane ve 0 öneki aynen)."""
    out = []
    for token in normalize(text).split():
        if _DIGITS.match(token) and len(token) <= 6 and not token.startswith("0"):
            out.append(number_to_words(int(token)))
        else:
            out.append(token)
    return " ".join(out)


def load_terms(path: Path = TERMS_PATH) -> dict[str, list[str]]:
    """Terim sözlüğü: sınıf -> normalleştirilmiş kök listesi (`_` anahtarları atlanır)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        cat: [_normalize_root(t) for t in terms]
        for cat, terms in raw.items()
        if not cat.startswith("_")
    }


def _normalize_root(term: str) -> str:
    """Kökü normalleştirir; baştaki `=` (tam eşleşme işareti) korunur."""
    exact = term.startswith(_EXACT)
    return (_EXACT if exact else "") + normalize(term.removeprefix(_EXACT))


def _token_matches(term_token: str, token: str, *, last: bool) -> bool:
    if term_token.startswith(_EXACT):
        return token == term_token[1:]
    return token == term_token or (last and token.startswith(term_token))


def _find_terms(tokens: list[str], terms: dict[str, list[str]]) -> list[tuple[str, str, int]]:
    """Belirteç dizisindeki terim geçişleri: (sınıf, kök, konum)."""
    found: list[tuple[str, str, int]] = []
    for cat, roots in terms.items():
        for root in roots:
            parts = root.split()
            for i in range(len(tokens) - len(parts) + 1):
                if all(
                    _token_matches(p, tokens[i + k], last=k == len(parts) - 1)
                    for k, p in enumerate(parts)
                ):
                    found.append((cat, root, i))
    return found


def term_accuracy(
    reference: str, hypothesis: str, terms: dict[str, list[str]]
) -> dict[str, tuple[int, int]]:
    """Sınıf başına (doğru, toplam): referanstaki terim geçişi çıktıda en az o kadar geçtiyse doğru.

    Sayım kök bazlıdır (min(referans, çıktı)), konum aramaz; bu yüzden fazla terim üretmek puan
    kazandırmaz ama sıralama hatası da cezalandırılmaz (sıra WER'in işidir).
    """
    ref_found = _find_terms(digits_to_words(reference).split(), terms)
    hyp_found = _find_terms(digits_to_words(hypothesis).split(), terms)
    ref_count = Counter((cat, root) for cat, root, _ in ref_found)
    hyp_count = Counter((cat, root) for cat, root, _ in hyp_found)
    result: dict[str, tuple[int, int]] = {}
    for (cat, root), total in ref_count.items():
        hit, all_ = result.get(cat, (0, 0))
        result[cat] = (hit + min(total, hyp_count[(cat, root)]), all_ + total)
    return result


def word_errors(reference: str, hypothesis: str) -> list[tuple[str, str, str]]:
    """Kelime düzeyinde hizalanmış hatalar: (tür, referans sözcük(ler), çıktı sözcük(ler)).

    Tür: `değişti` (yanlış yazım), `silindi` (çıktıda yok), `eklendi` (referansta yok).
    """
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    errors: list[tuple[str, str, str]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=ref, b=hyp, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        kind = {"replace": "değişti", "delete": "silindi", "insert": "eklendi"}[op]
        errors.append((kind, " ".join(ref[i1:i2]), " ".join(hyp[j1:j2])))
    return errors


def error_class(ref_words: str, terms: dict[str, list[str]]) -> str:
    """Hatalı referans sözcüğünün sınıfı: terim sınıfı (marka, parca...) ya da `genel`."""
    found = _find_terms(ref_words.split(), terms)
    return found[0][0] if found else "genel"


def is_format_only(ref_words: str, hyp_words: str) -> bool:
    """Fark yalnız yazım biçimiyse doğru: rakam/sözcük ("on beş" ~ "15") ya da ek ayrımı
    ("marina da" ~ "marinada"). Bunlar tanıma hatası değil, referans yazım tercihidir."""
    ref = digits_to_words(ref_words).replace(" ", "")
    hyp = digits_to_words(hyp_words).replace(" ", "")
    return bool(ref) and ref == hyp

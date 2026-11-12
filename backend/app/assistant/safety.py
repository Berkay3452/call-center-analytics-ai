"""Küfür, hakaret ve güvenlik politikası: LLM'e gitmeden önce kuralla uygulanır (#213).

Politika:
- **Hakaret/küfür (yalnızca):** sakin, kısa, saygılı, konuya yönlendiren hazır cevap. Küfür
  yansıtılmaz, tartışılmaz. Aynı oturumda tekrarlanırsa nazik ama net bir sınır cümlesi eklenir.
- **Küfür + gerçek soru** ("Lan bu ay ne kadar harcadım amk"): küfür ayıklanır, soru normal
  cevaplanır. Kullanıcı mesajı olduğu gibi kaydedilir; cevap ve loglar küfür taşımaz.
- **Cinsel içerik, şiddet tehdidi:** hazır, kısa ret; tartışma yok.
- **Kendine zarar ifadesi:** destekleyici hazır cevap ve 112 yönlendirmesi.
- **Başkasının verisi:** "başka müşteri", "herkesin giderleri", başka bir müşterinin adı: ret.

Kural tabanlıdır; çünkü hızlıdır (LLM çağrısı yok), her seferinde aynı sonucu verir ve hazır
cevaplar küfrü yankılayamaz. Sözlüğün yakalamadığı hakaretler (ör. "hiçbir işe yaramıyorsun") LLM
yoluna gider; orada `general.md` aynı politikayı uygular.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.agents.grounding import normalize
from app.schemas.assistant import HistoryTurn

CAPABILITIES = (
    "Teknenizin bakım geçmişi, giderleriniz veya aboneliğiniz hakkında yardımcı olabilirim."
)


class Violation(StrEnum):
    ABUSE = "hakaret"
    SEXUAL = "cinsel"
    THREAT = "tehdit"
    SELF_HARM = "kendine_zarar"


# Normalize edilmiş (aksansız, küçük harf) sözcükler. "mal", "sik" gibi başka anlamı olabilen
# kısa sözcükler yalnızca tam eşleşmeyle aranır; öbürleri kök (önek) olarak.
_ABUSE_EXACT = frozenset(
    {
        "sik", "sikik", "sikim", "sktr", "sktir", "amk", "amq", "aq", "mk", "oc", "pic", "got",
        "bok", "pust", "ibne", "kahpe", "yarak", "serefsiz", "haysiyetsiz", "aptal", "salak",
        "gerizekali", "gerzek", "embesil", "dangalak", "budala", "ahmak", "enayi", "moron",
    }
)  # fmt: skip
_ABUSE_PREFIX = (
    "siktir", "sikeyim", "sikerim", "sikik", "orospu", "oruspu", "pezevenk", "yarrak", "gotveren",
    "amina", "aminakoy", "anani", "ananin", "gerizekal", "salaksin", "aptalsin",
)  # fmt: skip
# "lan/ulan" tek başına küfür sayılmaz (hitap); yalnızca başka bir küfürle birlikteyse ayıklanır.
_ADDRESS_ONLY = frozenset({"lan", "ulan"})
_SEXUAL = frozenset({"seks", "sex", "porno", "porn", "ciplak", "erotik", "sevisme", "sevisek"})
_THREAT_TARGET = frozenset({"seni", "sizi"})
_THREAT_PREFIX = ("oldur", "gebert", "pataklay", "dovece", "dover", "vuraca", "bitirece")
_SELF_HARM = (
    "intihar", "kendimi oldur", "kendime zarar", "yasamak istemiyorum", "olmek istiyorum",
)  # fmt: skip

_LEET = str.maketrans({"1": "i", "0": "o", "3": "e", "@": "a", "$": "s", "4": "a", "5": "s"})
_SPACED_LETTERS = re.compile(r"(?<!\S)(?:\S(?: |$)){3,}")


@dataclass(frozen=True)
class Moderation:
    violation: Violation
    cleaned: str  # küfür sözcükleri ayıklanmış soru (boş olabilir)


def _squash_spaced(text: str) -> str:
    """ "a m k" → "amk": harfleri aralıklı yazarak sözlükten kaçmayı engeller."""
    return _SPACED_LETTERS.sub(lambda m: m.group(0).replace(" ", "") + " ", text)


def _tokens(text: str) -> list[str]:
    """Küfür aramak için sözcükler: "s1ktir" → "siktir" (rakamlı yazımlar harfe çevrilir)."""
    out = []
    for word in _squash_spaced(text).split():
        if any(c.isalpha() for c in word) and any(c.isdigit() or c in "@$" for c in word):
            word = word.translate(_LEET)
        out.extend(normalize(word).split())
    return out


def _is_abuse_token(token: str) -> bool:
    if token in _ADDRESS_ONLY:
        return False
    return token in _ABUSE_EXACT or token.startswith(_ABUSE_PREFIX)


def moderate(question: str) -> Moderation | None:
    """Mesajda ihlal varsa türü ve küfürden arındırılmış hâli; yoksa None."""
    tokens = _tokens(question)
    text = " ".join(tokens)
    if any(re.search(r"\b" + p, text) for p in _SELF_HARM):
        return Moderation(Violation.SELF_HARM, "")
    if _THREAT_TARGET & set(tokens) and any(t.startswith(_THREAT_PREFIX) for t in tokens):
        return Moderation(Violation.THREAT, "")
    if (_SEXUAL & set(tokens)) or (
        "seninle" in tokens and any(t.startswith("yat") for t in tokens)
    ):
        return Moderation(Violation.SEXUAL, "")
    if any(_is_abuse_token(t) for t in tokens):
        kept = [w for w in question.split() if not _word_is_abusive(w)]
        return Moderation(Violation.ABUSE, " ".join(kept).strip(" ,.!?"))
    return None


def _word_is_abusive(word: str) -> bool:
    toks = _tokens(word)
    return bool(toks) and all(_is_abuse_token(t) or t in _ADDRESS_ONLY for t in toks)


def contains_profanity(text: str) -> bool:
    """Oturum başlığı gibi görünür yerlere küfür sızmasın diye hızlı kontrol."""
    return moderate(text) is not None


def is_repeat_offense(history: list[HistoryTurn]) -> bool:
    """Oturumda daha önce küfür/hakaret ya da benzeri bir ihlal var mı?"""
    return any(t.role == "user" and moderate(t.content) is not None for t in history)


# --- Hazır cevaplar ---------------------------------------------------------------------------

ABUSE_REPLY = (
    "Sizi kızdıran bir şey olduysa üzgünüm. Bir sorununuz varsa Miço Usta servis ekibine "
    f'iletebilirim. {CAPABILITIES} Örneğin: "Bu ay ne kadar harcadım?" diye sorabilirsiniz.'
)
ABUSE_REPEAT_REPLY = (
    "Saygılı bir dille devam edersek size daha iyi yardımcı olabilirim. "
    f"Teknenizle ilgili bir sorunuz olursa buradayım. {CAPABILITIES}"
)
SEXUAL_REPLY = (
    "Bu tür konularda konuşmuyorum. Teknenizle ilgili sorularınızda yardımcı olabilirim: "
    "bakım geçmişi, giderler ve paket hakkınız."
)
THREAT_REPLY = (
    "Şiddet içeren ifadelere cevap veremem. Bir memnuniyetsizliğiniz varsa Miço Usta servis "
    f"ekibine iletebilirsiniz. {CAPABILITIES}"
)
SELF_HARM_REPLY = (
    "Bunu duyduğuma üzüldüm. Kendinize zarar verme düşünceniz varsa lütfen hemen 112 Acil Çağrı "
    "Merkezi'ni arayın ve yakınlarınızdan destek isteyin. Yalnız değilsiniz."
)
NOT_UNDERSTOOD_REPLY = (
    "Mesajınızı anlayamadım. Teknenizin bakım geçmişi, giderleriniz veya aboneliğiniz hakkında "
    "bir soru yazabilir misiniz?"
)


def moderation_reply(violation: Violation, *, repeat: bool) -> str:
    if violation == Violation.SELF_HARM:
        return SELF_HARM_REPLY
    if violation == Violation.SEXUAL:
        return SEXUAL_REPLY
    if violation == Violation.THREAT:
        return THREAT_REPLY
    return ABUSE_REPEAT_REPLY if repeat else ABUSE_REPLY


def has_no_words(question: str) -> bool:
    """Harf içermeyen mesaj ("???", "1234567", emoji): LLM'e gitmeden "anlayamadım"."""
    return not any(c.isalpha() for c in question)


# --- Başkasının verisi --------------------------------------------------------------------------

_OTHER_PARTY_PHRASES = (
    "baska musteri", "diger musteri", "baska kullanici", "diger kullanici", "baskasinin",
    "baska birinin", "herkesin", "tum musteri", "butun musteri", "musterilerin", "musterilerinin",
    "baska tekne sahib", "diger tekne sahib", "baska teknelerin", "diger teknelerin",
)  # fmt: skip


def asks_other_party(question: str) -> bool:
    """ "Başka müşterilerin giderleri", "herkesin teknesi" gibi başkasının verisini isteyen soru."""
    text = f" {normalize(question)} "
    return any(f" {p}" in text for p in _OTHER_PARTY_PHRASES)


def mentions_other_customer(question: str, other_names: set[str]) -> bool:
    """Soruda başka bir müşterinin tam adı (normalize edilmiş) geçiyor mu?"""
    text = f" {normalize(question)} "
    return any(f" {name} " in text for name in other_names)


# --- Kural aşma girişimi, başkasının verisi, anlamsız metin: duruma özel cevaplar ---

_INJECTION_PHRASES = (
    "ignore previous",
    "ignore all",
    "ignore the above",
    "disregard previous",
    "previous instructions",
    "system prompt",
    "reveal your prompt",
    "show your prompt",
    "developer mode",
    "jailbreak",
    "onceki talimat",
    "onceki komut",
    "talimatlari unut",
    "talimatlarini unut",
    "kurallari unut",
    "talimatlarini yaz",
    "talimatlarini goster",
    "talimatlarini soyle",
    "sistem talimat",
    "sistem komut",
    "sistem mesaj",
    "sistem prompt",
    "promptunu",
    "prompt u goster",
    "rolunu unut",
    "kuralsiz",
    "tum verileri goster",
    "butun verileri goster",
    "tum veriyi goster",
    "butun veriyi goster",
    "show all data",
    "dump the database",
    "veritabanini goster",
    "veritabanini dok",
    "api anahtar",
    "api key",
    "gizli anahtar",
    "owner id",
    "ownerid",
)  # fmt: skip

INJECTION_REPLIES = (
    "Sistem talimatlarımı, ayarlarımı veya gizli bilgileri paylaşamam ve kurallarımı "
    f'değiştiremem. {CAPABILITIES} Örneğin: "Kaç bakım hakkım kaldı?" diye sorabilirsiniz.',
    "Bu isteği yerine getiremem: iç ayarlarım ve verilerin tamamı paylaşılmaz. Yalnızca kendi "
    f"teknenizin kayıtlarına bakabilirim. {CAPABILITIES}",
    "Talimatlarımı değiştirmem veya sistem bilgilerini göstermem mümkün değil. Teknenizle ilgili "
    "bir şey öğrenmek isterseniz buradayım: bakım geçmişi, giderler, paket hakkınız.",
)
OTHER_PARTY_REPLIES = (
    "Başka müşterilerin bilgilerini paylaşamam; gizlilik gereği yalnızca kendi teknenizin ve "
    f"hesabınızın kayıtlarına bakabilirim. {CAPABILITIES}",
    "Diğer müşterilere ait gider veya kayıtları gösteremem. Kendi giderlerinizi görmek için "
    '"Bu ay ne kadar harcadım?" diye sorabilirsiniz.',
    "Bu bilgi başka bir müşteriye ait olduğu için erişemiyorum. Kendi teknenizin bakım geçmişi "
    "ve giderleri hakkında yardımcı olabilirim.",
)
OUT_OF_SCOPE_REPLIES = (
    "Bu konu benim alanımın dışında kalıyor. Teknenizin bakım geçmişi, giderleriniz ve "
    "aboneliğiniz hakkında yardımcı olabilirim.",
    "Bu isteğe yardımcı olamıyorum; ben Miço Usta'nın tekne asistanıyım. Bakım kayıtlarınızı, "
    "giderlerinizi veya paket hakkınızı sorabilirsiniz.",
    "Maalesef bu konuda yardımcı olamıyorum. Teknenizle ilgili kayıtlar, giderler ve bakım "
    "önerileri konusunda buradayım.",
)  # fmt: skip


def pick_reply(options: tuple[str, ...], question: str) -> str:
    """Aynı soruya hep aynı, farklı sorulara farklı cevap (deterministik çeşitleme)."""
    return options[sum(ord(c) for c in question) % len(options)]


# SQL/betik benzeri girdiler: sorgu çalıştırılmaz ama "takip sorusu" sanılıp önceki cevabı
# tekrarlatmamalı (web testi bulgusu #4).
_CODE_LIKE = re.compile(
    r"(\b(drop|truncate|alter|delete|insert|update|select)\b.{0,40}\b(table|from|into|set|database)\b"
    r"|\bunion\s+select\b|\bor\s+1\s*=\s*1\b|;\s*--|<\s*script|\bexec(ute)?\s*\()",
    re.IGNORECASE | re.DOTALL,
)


def is_injection_attempt(question: str) -> bool:
    """Talimatları unutturma, sistem istemini veya tüm veriyi isteme, SQL/betik enjeksiyonu."""
    if _CODE_LIKE.search(question):
        return True
    text = f" {normalize(question)} "
    return any(f" {p}" in text for p in _INJECTION_PHRASES)


_VOWELS = frozenset("aeiou")
_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{5,}")


def _bad_token(token: str) -> bool:
    letters = [c for c in token if c.isalpha()]
    if not letters:
        return False
    if len(letters) >= 20:
        return True
    vowels = sum(1 for c in letters if c in _VOWELS)
    return bool(_CONSONANT_RUN.search(token)) or (len(letters) >= 3 and vowels == 0)


def looks_like_gibberish(question: str) -> bool:
    """Klavye rastgeleliği ("asdfgh jkl", "asdıuyasasjhjh...") gibi anlamsız harf dizileri."""
    tokens = [t for t in normalize(question).split() if any(c.isalpha() for c in t)]
    if not tokens:
        return False
    bad = sum(1 for t in tokens if _bad_token(t))
    return bad > 0 and bad * 2 >= len(tokens)

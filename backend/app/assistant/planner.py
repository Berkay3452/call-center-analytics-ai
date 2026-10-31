"""Sorgu planlayıcı: soruyu sınıflar (gecmis_oneri / sayisal / kapsam_disi) ve aracı seçer.

Üç katmanlıdır:
0. Sohbet cümleleri (selam, teşekkür, "sen kimsin"): `smalltalk_reply` ile LLM'siz hazır cevap.
1. Kurallar: net sayısal sorular ("ne kadar harcadım", "kaç hakkım kaldı", "son bakım ne
   zaman") LLM çağrısı yapılmadan sınıflanır. Hem hızlıdır hem ücretsiz katmanın kotasını korur.
2. LLM (hızlı model): kuralların yakalamadığı her şey için.

Planlayıcı soruyu cevaplamaz ve `owner_id` ile ilgilenmez; yetki araçlarda ve aramada uygulanır.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.grounding import normalize
from app.assistant.llm import AssistantLLM, load_prompt
from app.schemas.assistant import AssistantTool, QuestionType

Period = Literal["bu_ay", "tumu"]


class Plan(BaseModel):
    """Planlayıcının çıktısı (LLM'den de bu şemayla JSON beklenir)."""

    question_type: QuestionType = Field(description="Sorunun sınıfı.")
    tool: AssistantTool | None = Field(
        default=None, description="Yalnızca sayisal sorularda doldurulur, diğerlerinde null."
    )
    period: Period = Field(default="tumu", description="Gider sorularında dönem.")

    @model_validator(mode="after")
    def _tool_only_for_numeric(self) -> "Plan":
        numeric = self.question_type == QuestionType.SAYISAL
        if numeric and self.tool is None:
            raise ValueError("question_type=sayisal iken tool zorunludur.")
        if not numeric and self.tool is not None:
            raise ValueError("tool yalnızca question_type=sayisal iken verilebilir.")
        return self


def _has(tokens: list[str], *prefixes: str) -> bool:
    return any(t.startswith(p) for t in tokens for p in prefixes)


# Belirli bir parça ya da işi anan kökler (normalize edilmiş). Soru bir konu söylüyorsa genel
# toplam araçları yanlış cevap verir ("akü için ne kadar ödedim" ≠ tüm giderler).
_TOPIC_PREFIXES = (
    "aku", "filtre", "impeller", "motor", "jenerator", "boya", "pompa", "yag", "pervane", "anot",
    "kayis", "sintine", "garanti", "yakit", "elektrik", "klima", "vinc",
)  # fmt: skip


def mentions_topic(tokens: list[str]) -> bool:
    return _has(tokens, *_TOPIC_PREFIXES)


def plan_by_rules(question: str) -> Plan | None:
    """Net sayısal sorular için plan; belirsizse None (LLM'e bırakılır)."""
    text = normalize(question)
    tokens = text.split()
    period: Period = "bu_ay" if "bu ay" in text else "tumu"

    if _has(tokens, "harca", "masraf", "gider", "odeme", "odedi", "fatura") and not mentions_topic(
        tokens
    ):
        return Plan(
            question_type=QuestionType.SAYISAL, tool=AssistantTool.GET_EXPENSE_TOTAL, period=period
        )
    if _has(tokens, "paket", "abone") or (_has(tokens, "hak") and _has(tokens, "kal")):
        return Plan(question_type=QuestionType.SAYISAL, tool=AssistantTool.GET_REMAINING_PACKAGE)
    if (
        "yakinda" in tokens
        or _has(tokens, "yaklasan", "planli")
        or ("yapilmasi gereken" in text or "yapmam gereken" in text)
    ):
        return Plan(question_type=QuestionType.SAYISAL, tool=AssistantTool.GET_UPCOMING_MAINTENANCE)
    if (
        "son" in tokens
        and _has(tokens, "bakim", "servis")
        and (_has(tokens, "zaman", "tarih") or "ne zaman" in text)
    ):
        return Plan(question_type=QuestionType.SAYISAL, tool=AssistantTool.GET_LAST_MAINTENANCE)
    return None


async def plan_question(question: str, llm: AssistantLLM) -> Plan:
    """Önce kurallar, yoksa hızlı LLM ile sınıflar."""
    if (plan := plan_by_rules(question)) is not None:
        return plan
    return await llm.ask(
        "fast",
        load_prompt("planner"),
        f"## Tekne sahibinin sorusu\n{question}",
        Plan,
    )


# --- Selam / teşekkür / "sen kimsin": LLM'siz hazır cevaplar (#161) -------------------------------

CAPABILITIES_HINT = (
    "Tekneniz, bakım kayıtlarınız, giderleriniz veya aboneliğiniz hakkında soru sorabilirsiniz."
)
EXAMPLE_QUESTIONS = (
    'Örneğin: "Bu ay ne kadar harcadım?", "Kaç bakım hakkım kaldı?" ya da '
    '"Yakıt filtresi için usta ne önermişti?"'
)
GREETING_REPLY = f"Merhaba! {CAPABILITIES_HINT} {EXAMPLE_QUESTIONS}"
THANKS_REPLY = f"Rica ederim! Başka bir sorunuz olursa buradayım. {CAPABILITIES_HINT}"
IDENTITY_REPLY = (
    "Ben Miço Usta'nın tekne asistanı Miço AI'yım. Teknenizin bakım geçmişi, giderleriniz ve "
    f"aboneliğiniz hakkında kayıtlarınıza dayanarak cevap veririm. {EXAMPLE_QUESTIONS}"
)
GOODBYE_REPLY = "Görüşmek üzere! Teknenizle ilgili sorularınız olursa tekrar yazabilirsiniz."

_ADDRESS_WORDS = frozenset({"mico", "usta", "ai", "asistan", "asistani", "bey", "hanim"})
_GREETING_WORDS = frozenset(
    {
        "merhaba", "merhabalar", "meraba", "selam", "selamlar", "selamun", "aleykum", "hey", "hi",
        "hello", "gunaydin", "tunaydin", "iyi", "gunler", "aksamlar", "geceler", "sabahlar",
        "naber", "nasilsin", "nasilsiniz", "nasil", "gidiyor", "misin", "misiniz", "ben",
        "bir", "sorum", "var", "yardim", "eder", "edebilir", "musun", "musunuz", "orada", "alo",
    }
)  # fmt: skip
_GREETING_CORE = frozenset(
    {
        "merhaba", "merhabalar", "meraba", "selam", "selamlar", "selamun", "hey", "hi", "hello",
        "gunaydin", "tunaydin", "gunler", "aksamlar", "geceler", "sabahlar", "naber", "nasilsin",
        "nasilsiniz", "gidiyor", "alo", "sorum", "yardim",
    }
)  # fmt: skip
_THANKS_WORDS = frozenset(
    {
        "tesekkur", "tesekkurler", "tesekkurle", "ederim", "ederiz", "cok", "sagol", "sag", "ol",
        "saol", "eyvallah", "mersi", "tamam", "super", "harika", "guzel", "oldu", "anladim",
        "yardimin", "icin", "yardimlariniz", "sagolun", "olun", "emegine", "saglik",
    }
)  # fmt: skip
_GOODBYE_PHRASES = ("gorusuruz", "hoscakal", "hosca kal", "bay bay", "baybay", "hosca kalin")
_IDENTITY_PHRASES = (
    "kimsin", "kimsiniz", "adin ne", "adiniz ne", "ismin ne", "nesin", "kendini tanit",
    "kendinizi tanit", "ne yapabilirsin", "neler yapabilirsin", "ne yapabilirsiniz",
    "neler yapabilirsiniz", "ne ise yararsin", "nasil yardimci olabilirsin",
    "nasil yardimci olabilirsiniz", "sen nesin", "kim yapti seni",
)  # fmt: skip
_MAX_SMALLTALK_TOKENS = 7


def smalltalk_reply(question: str) -> str | None:
    """Selam, teşekkür, veda ve "sen kimsin" gibi sohbet cümleleri için hazır cevap; yoksa None.

    Yalnızca kısa ve tamamı sohbet sözcüklerinden oluşan cümleleri yakalar ("Selam, bu ay ne
    kadar harcadım?" gibi gerçek soru içerenler planlayıcıya gider). Sayı/kayıt aramaz,
    LLM çağırmaz: anında döner.
    """
    tokens = [t for t in normalize(question).split() if t not in _ADDRESS_WORDS]
    if not tokens or len(tokens) > _MAX_SMALLTALK_TOKENS:
        return None
    text = " ".join(tokens)
    if any(f" {p} " in f" {text} " for p in _IDENTITY_PHRASES):
        return IDENTITY_REPLY
    if any(f" {p} " in f" {text} " for p in _GOODBYE_PHRASES):
        return GOODBYE_REPLY
    thanks_core = _has(tokens, "tesekkur", "sag", "saol", "eyval", "mersi")
    if thanks_core and all(t in _THANKS_WORDS for t in tokens):
        return THANKS_REPLY
    if all(t in _GREETING_WORDS for t in tokens) and any(t in _GREETING_CORE for t in tokens):
        return GREETING_REPLY
    return None

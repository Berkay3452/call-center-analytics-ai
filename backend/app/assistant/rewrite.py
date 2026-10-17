"""Takip sorusunu bağımsız soruya çevirir (#111).

"Peki ne yapılmıştı?" tek başına anlaşılmaz; oturum geçmişine bakılarak "15 Ağustos 2026'daki
bakımda ne yapılmıştı?" haline getirilir. Yeniden yazım yalnızca planlama ve arama içindir:
kullanıcıya gösterilmez, loga yazılır.

Gecikme eklememek için kurallı kısa yol vardır: geçmiş yoksa, soru net bir sayısal soruysa ya da
kendi başına anlaşılır görünüyorsa LLM çağrılmaz. LLM yalnızca gerçek takip sorularında çalışır
ve hata verirse özgün soru aynen kullanılır (yeniden yazım cevabı engellemez).
"""

import structlog
from pydantic import BaseModel, Field

from app.agents.grounding import normalize
from app.assistant.llm import AssistantLLM, AssistantLLMError, load_prompt
from app.assistant.planner import mentions_topic, plan_by_rules
from app.llm.client import LLMNotConfiguredError
from app.schemas.assistant import HistoryTurn

log = structlog.get_logger(__name__)

MAX_HISTORY_TURNS = 6
MAX_TURN_CHARS = 400
SHORT_QUESTION_TOKENS = 6

# Önceki konuşmaya gönderme yapan sözcükler (normalize edilmiş, tam eşleşme).
_CONTINUATION = frozenset(
    {
        "peki", "ya", "o", "onu", "onun", "bunu", "bunun", "sunu", "sunun", "orada", "onda",
        "ondan", "bundan", "ayni", "aynisi", "aynisini", "digeri", "digerleri", "bunlar",
        "onlar", "sonra", "oncesi", "oyleyse", "madem", "yani",
    }
)  # fmt: skip


class Rewrite(BaseModel):
    """LLM'den beklenen çıktı."""

    standalone_question: str = Field(
        min_length=1, max_length=1000, description="Tek başına anlaşılır soru."
    )


def looks_like_follow_up(question: str) -> bool:
    """Kurallı kısa yol: soru önceki konuşmaya bağlı görünüyor mu?"""
    if plan_by_rules(question) is not None:
        return False  # net sayısal soru: kendi başına anlaşılır
    tokens = normalize(question).split()
    if any(t in _CONTINUATION for t in tokens):
        return True
    return len(tokens) <= SHORT_QUESTION_TOKENS and not mentions_topic(tokens)


def _format_history(history: list[HistoryTurn]) -> str:
    lines = []
    for turn in history[-MAX_HISTORY_TURNS:]:
        who = "Tekne sahibi" if turn.role == "user" else "Asistan"
        lines.append(f"{who}: {turn.content.strip()[:MAX_TURN_CHARS]}")
    return "\n".join(lines)


async def standalone_question(question: str, history: list[HistoryTurn], llm: AssistantLLM) -> str:
    """Takip sorusunu geçmişe bakarak bağımsız hale getirir; gerek yoksa aynen döner."""
    if not history or not looks_like_follow_up(question):
        return question
    try:
        result = await llm.ask(
            "fast",
            load_prompt("rewrite"),
            f"## Önceki konuşma\n{_format_history(history)}\n\n## Yeni soru\n{question}",
            Rewrite,
        )
    except (AssistantLLMError, LLMNotConfiguredError):
        log.warning("assistant.rewrite_failed")
        return question
    rewritten = result.standalone_question.strip()
    log.info("assistant.rewritten", original=question, rewritten=rewritten)
    return rewritten or question

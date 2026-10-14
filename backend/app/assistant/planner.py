"""Sorgu planlayıcı: soruyu sınıflar (gecmis_oneri / sayisal / kapsam_disi) ve aracı seçer.

İki katmanlıdır:
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


def plan_by_rules(question: str) -> Plan | None:
    """Net sayısal sorular için plan; belirsizse None (LLM'e bırakılır)."""
    text = normalize(question)
    tokens = text.split()
    period: Period = "bu_ay" if "bu ay" in text else "tumu"

    if _has(tokens, "harca", "masraf", "gider", "odeme", "odedi", "fatura"):
        return Plan(
            question_type=QuestionType.SAYISAL, tool=AssistantTool.GET_EXPENSE_TOTAL, period=period
        )
    if _has(tokens, "paket", "abone") or (_has(tokens, "hak") and _has(tokens, "kal")):
        return Plan(question_type=QuestionType.SAYISAL, tool=AssistantTool.GET_REMAINING_PACKAGE)
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

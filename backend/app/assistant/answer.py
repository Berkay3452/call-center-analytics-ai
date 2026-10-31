"""Cevap üretimi.

- **Sayısal sorular:** cümleyi ve sayıyı KOD kurar; LLM araya girmez, sayı uyduramaz.
- **Geçmiş/öneri soruları:** LLM, bulunan kayıtlara dayanarak kaynaklı ifadeler üretir
  (`AnswerDraft`); kaynak kontrolü (`grounding.py`) ifadeleri doğrular.
"""

import calendar
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import tools
from app.assistant.formatting import MONTHS, format_date, format_try
from app.assistant.grounding import NOT_FOUND_MESSAGE, AnswerDraft, ground_draft
from app.assistant.llm import AssistantLLM, AssistantLLMError, load_prompt
from app.assistant.planner import Plan
from app.assistant.retrieval import Passage
from app.schemas.assistant import AssistantAnswer, AssistantTool, QuestionType


def not_found(question_type: QuestionType, message: str = NOT_FOUND_MESSAGE) -> AssistantAnswer:
    return AssistantAnswer(answer=message, question_type=question_type, found=False)


async def numeric_answer(
    plan: Plan,
    owner_id: str,
    today: date,
    *,
    session: AsyncSession | None = None,
) -> AssistantAnswer:
    """Hazır aracı çalıştırıp cevabı kodla kurar."""
    qt = QuestionType.SAYISAL
    start: date | None
    end: date | None
    if plan.tool == AssistantTool.GET_EXPENSE_TOTAL:
        if plan.period == "bu_ay":
            start = today.replace(day=1)
            end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            label = f"{MONTHS[today.month - 1]} {today.year} döneminde"
        else:
            start = end = None
            label = "Kayıtlı tüm dönemde"
        result = await tools.get_expense_total(owner_id, start=start, end=end, session=session)
        if result.item_count == 0:
            return not_found(qt, "Bu dönem için kayıtlı bir gider bulamadım.")
        return AssistantAnswer(
            answer=(
                f"{label} toplam giderleriniz {format_try(result.total_try)} "
                f"({result.item_count} kalem)."
            ),
            question_type=qt,
            sources=result.sources,
        )
    if plan.tool == AssistantTool.GET_REMAINING_PACKAGE:
        pkg = await tools.get_remaining_package(owner_id, session=session)
        if pkg is None:
            return not_found(qt, "Kayıtlarda aktif bir abonelik veya paket bulamadım.")
        return AssistantAnswer(
            answer=(
                f"{pkg.plan} paketinizde {pkg.remaining} bakım hakkınız kaldı "
                f"({pkg.total} hakkın {pkg.total - pkg.remaining}'i kullanıldı). "
                f"Paket {format_date(pkg.ends_on)} tarihinde sona eriyor."
            ),
            question_type=qt,
            sources=pkg.sources,
        )
    if plan.tool == AssistantTool.GET_LAST_MAINTENANCE:
        last = await tools.get_last_maintenance(owner_id, session=session)
        if last is None:
            return not_found(qt, "Kayıtlarda yapılmış bir bakım bulamadım.")
        return AssistantAnswer(
            answer=(
                f"{last.boat_name} için son bakım {format_date(last.on)} tarihinde yapıldı: "
                f"{last.job} (usta: {last.craftsman})."
            ),
            question_type=qt,
            sources=last.sources,
        )
    if plan.tool == AssistantTool.GET_UPCOMING_MAINTENANCE:
        upcoming = await tools.get_upcoming_maintenance(owner_id, today=today, session=session)
        if not upcoming:
            return not_found(qt, NO_UPCOMING_MESSAGE)
        shown = upcoming[:MAX_UPCOMING_ITEMS]
        lines = [_upcoming_line(item) for item in shown]
        more = len(upcoming) - len(shown)
        tail = f"\n(ve {more} iş daha)" if more > 0 else ""
        return AssistantAnswer(
            answer="Teknelerinizde yakında yapılması gerekenler:\n" + "\n".join(lines) + tail,
            question_type=qt,
            sources=[src for item in shown for src in item.sources],
        )
    raise ValueError(f"Bilinmeyen araç: {plan.tool}")


NO_UPCOMING_MESSAGE = (
    "Kayıtlarınıza göre yakında yapılması gereken veya planlanmış bir iş görünmüyor."
)
MAX_UPCOMING_ITEMS = 6


def _upcoming_line(item: tools.UpcomingItem) -> str:
    when = format_date(item.due_on) if item.due_on else "tarih belirsiz"
    if item.overdue:
        when += ", gecikmiş"
    boat = f"{item.boat_name}: " if item.boat_name else ""
    return f"- {boat}{item.what} ({when}; {item.reason})"


class GeneralReply(BaseModel):
    """Genel (kayıtsız) cevap; LLM'den bu şemayla JSON beklenir."""

    answer: str = Field(max_length=2000, description="Kullanıcıya gösterilecek cevap metni.")


NOT_IN_RECORDS_PREFIX = "Kayıtlarınızda bu konuda bir bilgi bulamadım. Genel olarak şöyle:"
EMPTY_GENERAL_MESSAGE = (
    "Bu soruya şu an cevap veremiyorum. Teknenizin kayıtlarıyla ilgili soru sorabilirsiniz."
)


async def general_answer(question: str, llm: AssistantLLM) -> AssistantAnswer:
    """Kayıt gerektirmeyen sorular: doğrudan LLM cevabı, kaynak kartı yok (#177)."""
    reply = await llm.ask(
        "fast", load_prompt("general"), f"## Tekne sahibinin sorusu\n{question}", GeneralReply
    )
    text = reply.answer.strip() or EMPTY_GENERAL_MESSAGE
    return AssistantAnswer(answer=text, question_type=QuestionType.GENEL_SOHBET)


async def not_found_with_general_info(
    question: str, llm: AssistantLLM, qt: QuestionType
) -> AssistantAnswer:
    """Kayıt gerektiren ama kayıtta bulunamayan soru: "bulamadım" + ayrı genel bilgi.

    Kaynak kartı yoktur (genel bilgi kayda dayanmaz), `found=False` kalır. LLM cevap veremezse
    eski "bulamadım" mesajına düşer; bu ek adımın hatası kullanıcıya yansımaz.
    """
    try:
        reply = await llm.ask(
            "fast",
            load_prompt("general_fallback"),
            f"## Tekne sahibinin sorusu\n{question}",
            GeneralReply,
            max_fix_attempts=0,
        )
    except AssistantLLMError:
        return not_found(qt)
    text = reply.answer.strip()
    if not text:
        return not_found(qt)
    return not_found(qt, f"{NOT_IN_RECORDS_PREFIX}\n\n{text}")


async def history_answer(
    question: str, passages: list[Passage], llm: AssistantLLM
) -> AssistantAnswer:
    """Bulunan kayıtlardan kaynaklı cevap üretir ve kaynak kontrolünden geçirir.

    Kayıt yoksa ya da hiçbir ifade kaynakla doğrulanamazsa "bulamadım" + genel bilgi döner.
    """
    qt = QuestionType.GECMIS_ONERI
    if not passages:
        return await not_found_with_general_info(question, llm, qt)
    records = "\n".join(f"[{p.source.record_id}] ({p.source.title}) {p.text}" for p in passages)
    draft = await llm.ask(
        "smart",
        load_prompt("answer"),
        f"## Tekne sahibinin sorusu\n{question}\n\n## Kayıtlar\n{records}",
        AnswerDraft,
    )
    grounded = ground_draft(draft, passages)
    if grounded is None:
        return await not_found_with_general_info(question, llm, qt)
    text, sources = grounded
    return AssistantAnswer(answer=text, question_type=qt, sources=sources)

"""Cevap üretimi.

- **Sayısal sorular:** cümleyi ve sayıyı KOD kurar; LLM araya girmez, sayı uyduramaz.
- **Geçmiş/öneri soruları:** LLM, bulunan kayıtlara dayanarak kaynaklı ifadeler üretir
  (`AnswerDraft`); kaynak kontrolü (`grounding.py`) ifadeleri doğrular.
"""

import calendar
from datetime import date
from decimal import Decimal

from app.assistant import tools
from app.assistant.grounding import NOT_FOUND_MESSAGE, AnswerDraft, ground_draft
from app.assistant.llm import AssistantLLM, load_prompt
from app.assistant.planner import Plan
from app.assistant.retrieval import Passage
from app.schemas.assistant import AssistantAnswer, AssistantTool, QuestionType

_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]  # fmt: skip


def format_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def format_try(amount: Decimal) -> str:
    """14250.00 → '14.250,00 TL' (Türkçe sayı biçimi)."""
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} TL"


def not_found(question_type: QuestionType, message: str = NOT_FOUND_MESSAGE) -> AssistantAnswer:
    return AssistantAnswer(answer=message, question_type=question_type, found=False)


def numeric_answer(plan: Plan, owner_id: str, today: date) -> AssistantAnswer:
    """Hazır aracı çalıştırıp cevabı kodla kurar."""
    qt = QuestionType.SAYISAL
    start: date | None
    end: date | None
    if plan.tool == AssistantTool.GET_EXPENSE_TOTAL:
        if plan.period == "bu_ay":
            start = today.replace(day=1)
            end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            label = f"{_MONTHS[today.month - 1]} {today.year} döneminde"
        else:
            start = end = None
            label = "Kayıtlı tüm dönemde"
        result = tools.get_expense_total(owner_id, start=start, end=end)
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
        pkg = tools.get_remaining_package(owner_id)
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
        last = tools.get_last_maintenance(owner_id)
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
    raise ValueError(f"Bilinmeyen araç: {plan.tool}")


async def history_answer(
    question: str, passages: list[Passage], llm: AssistantLLM
) -> AssistantAnswer:
    """Bulunan kayıtlardan kaynaklı cevap üretir ve kaynak kontrolünden geçirir."""
    qt = QuestionType.GECMIS_ONERI
    if not passages:
        return not_found(qt)
    records = "\n".join(f"[{p.source.record_id}] ({p.source.title}) {p.text}" for p in passages)
    draft = await llm.ask(
        "smart",
        load_prompt("answer"),
        f"## Tekne sahibinin sorusu\n{question}\n\n## Kayıtlar\n{records}",
        AnswerDraft,
    )
    grounded = ground_draft(draft, passages)
    if grounded is None:
        return not_found(qt)
    text, sources = grounded
    return AssistantAnswer(answer=text, question_type=qt, sources=sources)

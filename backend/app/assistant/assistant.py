"""Miço AI'nın dışa açılan tek giriş noktası: `answer_question`.

Akış (diyagram 03): planlayıcı → [tekne karnesi araması | hazır araçlar | nazik ret] →
cevap üret → kaynak kontrolü. Sohbet API'si (#28) yalnızca bu fonksiyonu çağırır.
"""

from datetime import date

import structlog

from app.assistant.answer import history_answer, numeric_answer
from app.assistant.llm import AssistantLLM
from app.assistant.planner import plan_question
from app.assistant.retrieval import search_boat_notes
from app.schemas.assistant import AssistantAnswer, AssistantRequest, QuestionType

log = structlog.get_logger(__name__)

REFUSAL_MESSAGE = (
    "Ben Miço Usta'nın tekne asistanıyım; teknenizin bakım geçmişi, giderleriniz ve "
    "aboneliğiniz hakkında yardımcı olabilirim. Bu konuda size yardımcı olamıyorum."
)


async def answer_question(
    request: AssistantRequest,
    *,
    llm: AssistantLLM | None = None,
    today: date | None = None,
) -> AssistantAnswer:
    """Tekne sahibinin sorusunu, yalnızca kendi kayıtlarına dayanarak cevaplar.

    `owner_id` şemada zorunludur (boşsa `AssistantRequest` oluşturulamaz). LLM hatasında
    `AssistantLLMError` yükselir; API bunu 503'e çevirir.
    """
    llm = llm or AssistantLLM()
    today = today or date.today()

    plan = await plan_question(request.question, llm)
    log.info("assistant.planned", question_type=plan.question_type, tool=plan.tool)

    if plan.question_type == QuestionType.KAPSAM_DISI:
        # Ret, "bulamadım" durumu değildir (found=True): arayüz düz mesajı gösterir.
        return AssistantAnswer(answer=REFUSAL_MESSAGE, question_type=plan.question_type)
    if plan.question_type == QuestionType.SAYISAL:
        return numeric_answer(plan, request.owner_id, today)
    passages = search_boat_notes(request.owner_id, request.question)
    return await history_answer(request.question, passages, llm)

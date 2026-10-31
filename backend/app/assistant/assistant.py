"""Miço AI'nın dışa açılan tek giriş noktası: `answer_question`.

Akış (diyagram 03): planlayıcı → [tekne karnesi araması | hazır araçlar | nazik ret] →
cevap üret → kaynak kontrolü. Takip sorusu (#111) planlayıcıdan önce bağımsız soruya çevrilir.
Sohbet API'si (#28) yalnızca bu fonksiyonu çağırır.
"""

from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.answer import general_answer, history_answer, numeric_answer
from app.assistant.llm import AssistantLLM
from app.assistant.planner import EXAMPLE_QUESTIONS, plan_question, smalltalk_reply
from app.assistant.retrieval import search_boat_notes
from app.assistant.rewrite import standalone_question
from app.schemas.assistant import AssistantAnswer, AssistantRequest, QuestionType

log = structlog.get_logger(__name__)

REFUSAL_MESSAGE = (
    "Ben Miço Usta'nın tekne asistanıyım; teknenizin bakım geçmişi, giderleriniz ve "
    "aboneliğiniz hakkında yardımcı olabilirim. Bu konuda size yardımcı olamıyorum. "
    f"{EXAMPLE_QUESTIONS}"
)


async def answer_question(
    request: AssistantRequest,
    *,
    llm: AssistantLLM | None = None,
    today: date | None = None,
    session: AsyncSession | None = None,
) -> AssistantAnswer:
    """Tekne sahibinin sorusunu, yalnızca kendi kayıtlarına dayanarak cevaplar.

    `owner_id` şemada zorunludur (boşsa `AssistantRequest` oluşturulamaz). LLM hatasında
    `AssistantLLMError` yükselir; API bunu 503'e çevirir.
    """
    llm = llm or AssistantLLM()
    today = today or date.today()

    # Selam / teşekkür / "sen kimsin": LLM ve arama olmadan anında (#161).
    if (reply := smalltalk_reply(request.question)) is not None:
        log.info("assistant.smalltalk")
        return AssistantAnswer(answer=reply, question_type=QuestionType.GENEL_SOHBET)

    question = await standalone_question(request.question, request.history, llm)
    plan = await plan_question(question, llm)
    log.info("assistant.planned", question_type=plan.question_type, tool=plan.tool)

    if plan.question_type == QuestionType.KAPSAM_DISI:
        # Ret, "bulamadım" durumu değildir (found=True): arayüz düz mesajı gösterir.
        return AssistantAnswer(answer=REFUSAL_MESSAGE, question_type=plan.question_type)
    if plan.question_type == QuestionType.GENEL_SOHBET:
        return await general_answer(question, llm)
    if plan.question_type == QuestionType.SAYISAL:
        return await numeric_answer(plan, request.owner_id, today, session=session)
    passages = await search_boat_notes(request.owner_id, question, session=session)
    return await history_answer(question, passages, llm)

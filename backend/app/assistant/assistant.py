"""Miço AI'nın dışa açılan tek giriş noktası: `answer_question`.

Akış (diyagram 03): planlayıcı → [tekne karnesi araması | hazır araçlar | nazik ret] →
cevap üret → kaynak kontrolü. Takip sorusu (#111) planlayıcıdan önce bağımsız soruya çevrilir.
Sohbet API'si (#28) yalnızca bu fonksiyonu çağırır.
"""

from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.grounding import normalize
from app.assistant import injection, safety, tools
from app.assistant.answer import general_answer, history_answer, numeric_answer
from app.assistant.boats import foreign_boat_reply, resolve_boat
from app.assistant.llm import AssistantLLM
from app.assistant.planner import (
    mentions_topic,
    plan_by_rules,
    plan_question,
    smalltalk_reply,
)
from app.assistant.retrieval import search_boat_notes
from app.assistant.rewrite import standalone_question
from app.domain.audit import AuditAction, AuditActorRole, AuditOutcome
from app.schemas.assistant import AssistantAnswer, AssistantRequest, QuestionType
from app.services.audit import record_audit_event

log = structlog.get_logger(__name__)

MAX_PROCESSED_CHARS = 1000


async def _audit_safety(
    session: AsyncSession | None, request: AssistantRequest, action: AuditAction, **details: str
) -> None:
    """Güvenlik tetikleyicisini denetim günlüğüne ekler (#267). Soru metni yazılmaz; yalnızca
    tetikleyen kural türü. Kayıt, sohbet turunun işlemiyle birlikte kalıcı olur."""
    if session is None:
        return
    await record_audit_event(
        session,
        action=action,
        actor_id=request.owner_id,
        actor_role=AuditActorRole.TEKNE_SAHIBI,
        target_type="assistant",
        outcome=AuditOutcome.REDDEDILDI,
        details=details,
    )


async def _is_injection(
    request: AssistantRequest, llm: AssistantLLM, session: AsyncSession | None
) -> bool:
    """Kural katmanı saldırı derse ret; şüphe varsa hızlı LLM sınıflandırıcı karar verir (#273)."""
    detection = injection.inspect_input(request.question, request.history)
    layer = "kural"
    if detection.verdict is injection.Verdict.CLEAN:
        return False
    if detection.verdict is injection.Verdict.SUSPICIOUS:
        if safety.moderate(request.question) is not None:
            return False  # küfür/tehdit LLM çağırmadan hazır cevapla karşılanır
        verdict = await injection.classify_suspicious(request.question, request.history, llm)
        if verdict is None or not verdict.attack:
            return False
        layer = "llm"
        detection.category = verdict.category if verdict.category != "yok" else detection.category
    log.info("assistant.injection_attempt", layer=layer, category=detection.category)
    try:
        await _audit_safety(
            session,
            request,
            AuditAction.ASISTAN_INJECTION,
            kural="girdi_deseni" if layer == "kural" else "llm_siniflandirici",
            katman=layer,
            kategori=detection.category or "yok",
        )
    except Exception:  # denetim yazımı başarısız olsa da ret cevabı verilir
        log.warning("assistant.injection_audit_failed", layer=layer)
    return True


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

    # Selam / teşekkür / "sen kimsin" / saat-tarih: LLM ve arama olmadan anında (#161, #213).
    if (reply := smalltalk_reply(request.question)) is not None:
        log.info("assistant.smalltalk")
        return AssistantAnswer(answer=reply, question_type=QuestionType.GENEL_SOHBET)

    # Çok uzun metin: ilk 1000 karakter işlenir (planlayıcı ve arama için yeterli, maliyet sınırlı).
    if len(request.question) > MAX_PROCESSED_CHARS:
        request = request.model_copy(update={"question": request.question[:MAX_PROCESSED_CHARS]})

    # Prompt injection (#273): normalizasyon + kural katmanı; yalnızca şüphelide LLM sınıflandırıcı.
    # Moderasyondan ve anlamsız-metin denetiminden ÖNCE: kodlanmış yük "anlamsız" görünebilir.
    if await _is_injection(request, llm, session):
        return AssistantAnswer(
            answer=safety.pick_reply(safety.INJECTION_REPLIES, request.question),
            question_type=QuestionType.KAPSAM_DISI,
        )

    # Güvenlik katmanı (#213): küfür/cinsel/tehdit/kendine zarar ve harfsiz mesajlar LLM'e gitmez.
    question_text = request.question
    if (verdict := safety.moderate(question_text)) is not None:
        log.info("assistant.moderated", violation=verdict.violation)
        await _audit_safety(
            session, request, AuditAction.ASISTAN_KURAL_IHLALI, ihlal=verdict.violation.value
        )
        has_question = bool(verdict.cleaned) and verdict.violation == safety.Violation.ABUSE
        if has_question and (
            plan_by_rules(verdict.cleaned) is not None
            or mentions_topic(normalize(verdict.cleaned).split())
        ):
            question_text = verdict.cleaned  # küfür ayıklanır, gerçek soru cevaplanır
        else:
            reply = safety.moderation_reply(
                verdict.violation, repeat=safety.is_repeat_offense(request.history)
            )
            return AssistantAnswer(answer=reply, question_type=QuestionType.GENEL_SOHBET)
    elif safety.has_no_words(question_text) or safety.looks_like_gibberish(question_text):
        return AssistantAnswer(
            answer=safety.NOT_UNDERSTOOD_REPLY, question_type=QuestionType.GENEL_SOHBET
        )
    if safety.asks_other_party(question_text):
        await _audit_safety(session, request, AuditAction.ASISTAN_BASKA_TARAF, kural="baska_taraf")
        return AssistantAnswer(
            answer=safety.pick_reply(safety.OTHER_PARTY_REPLIES, question_text),
            question_type=QuestionType.KAPSAM_DISI,
        )
    if safety.mentions_other_customer(
        question_text, await tools.other_customer_names(request.owner_id, session=session)
    ):
        log.info("assistant.other_party_name")
        await _audit_safety(
            session, request, AuditAction.ASISTAN_BASKA_TARAF, kural="baska_musteri"
        )
        return AssistantAnswer(
            answer=safety.pick_reply(safety.OTHER_PARTY_REPLIES, question_text),
            question_type=QuestionType.KAPSAM_DISI,
        )

    question = await standalone_question(question_text, request.history, llm)
    own_boats = await tools.owner_boats(request.owner_id, session=session)
    match = resolve_boat(
        question, own_boats, await tools.other_boat_names(request.owner_id, session=session)
    )
    if match.foreign:
        log.info("assistant.other_boat_name")
        await _audit_safety(session, request, AuditAction.ASISTAN_BASKA_TARAF, kural="baska_tekne")
        return AssistantAnswer(
            answer=foreign_boat_reply(own_boats), question_type=QuestionType.KAPSAM_DISI
        )
    plan = await plan_question(question, llm)
    log.info("assistant.planned", question_type=plan.question_type, tool=plan.tool)

    if plan.question_type == QuestionType.KAPSAM_DISI:
        # Ret, "bulamadım" durumu değildir (found=True): arayüz düz mesajı gösterir.
        return AssistantAnswer(
            answer=safety.pick_reply(safety.OUT_OF_SCOPE_REPLIES, question),
            question_type=plan.question_type,
        )
    if plan.question_type == QuestionType.GENEL_SOHBET:
        return await general_answer(question, llm)
    if plan.question_type == QuestionType.SAYISAL:
        return await numeric_answer(
            plan,
            request.owner_id,
            today,
            session=session,
            boat=match.boat,
            boat_count=len(own_boats),
        )
    passages = await search_boat_notes(
        request.owner_id,
        question,
        boat_id=match.boat.id if match.boat else None,
        session=session,
    )
    return await history_answer(question, passages, llm, match.boat)

"""Miço AI Asistan sohbet servisi (#28).

Kurallar:
- Kimlik `owner_id` (UUID) üzerinden zorunludur.
- Oturumlar `chat_sessions`, mesajlar ve kaynaklar `chat_messages` tablolarına kaydedilir.
- Başka bir kullanıcının oturumuna erişilemez (404 döner, varlığı sızdırılmaz).
- Cevap üretimi `app.assistant.assistant.answer_question` fonksiyonuyla yapılır.
- SSE akışı:
  - `/assistant/chat`: `token` -> `sources` -> `done` (hata: `error`)
  - `/chat/messages/stream`: `status` -> `delta` -> `done` (hata: `error`)
- HTTP bilmez; hata durumlarında `app.core.errors` sınıflarını fırlatır.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import ServerSentEvent

from app.assistant.assistant import answer_question
from app.assistant.llm import AssistantLLM, AssistantLLMError
from app.core.errors import AppError, NotFoundError
from app.db.models.ai import ChatMessage, ChatSession
from app.db.models.external import Customer
from app.llm.client import LLMNotConfiguredError
from app.schemas.api import (
    ChatMessageOut,
    ChatReply,
    ChatSessionDetail,
    ChatSessionOut,
)
from app.schemas.assistant import AssistantAnswer, AssistantRequest, QuestionType, SourceRef

log = structlog.get_logger(__name__)

GENERIC_ERROR_MESSAGE = "Beklenmeyen bir hata oluştu. Lütfen biraz sonra tekrar deneyin."
# Akış metnini parçalar arasında bekleme: cevap kelime kelime yazılıyormuş gibi görünsün.
STREAM_CHUNK_DELAY_S = 0.03
ASSISTANT_UNAVAILABLE_MESSAGE = (
    "Şu anda sorunuzu yanıtlayamıyorum. Lütfen biraz sonra tekrar deneyin."
)


def _chunk_text(text: str, chunk_size: int = 24) -> list[str]:
    """Cevap metnini akış için doğal boyutlarda kelime öbeklerine böler."""
    if not text:
        return []
    words = text.split(" ")
    chunks: list[str] = []
    current = ""
    for w in words:
        if not current:
            current = w
        elif len(current) + len(w) + 1 <= chunk_size:
            current += " " + w
        else:
            chunks.append(current + " ")
            current = w
    if current:
        chunks.append(current)
    return chunks


def _to_message_out(msg: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
        question_type=QuestionType(msg.question_type) if msg.question_type else None,
        sources=[SourceRef.model_validate(s) for s in (msg.sources or [])],
        found=msg.found,
    )


def _to_session_out(sess: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        id=sess.id,
        title=sess.title,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
    )


async def _verify_customer_exists(db: AsyncSession, owner_uuid: UUID) -> None:
    exists = await db.scalar(select(func.count(Customer.id)).where(Customer.id == owner_uuid))
    if not exists:
        raise NotFoundError("Tekne sahibi bulunamadı.")


async def get_or_create_session(
    db: AsyncSession,
    owner_uuid: UUID,
    session_id: UUID | None,
    first_question: str,
) -> ChatSession:
    """Mevcut oturumu doğrular veya yeni bir oturum oluşturur."""
    await _verify_customer_exists(db, owner_uuid)

    if session_id is not None:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.owner_id == owner_uuid,
        )
        chat_session = await db.scalar(stmt)
        if chat_session is None:
            raise NotFoundError("Sohbet oturumu bulunamadı.")
        return chat_session

    title = first_question.strip()[:60]
    now = datetime.now(UTC)
    chat_session = ChatSession(
        id=uuid4(),
        owner_id=owner_uuid,
        title=title,
        created_at=now,
        updated_at=now,
    )
    db.add(chat_session)
    await db.flush()
    return chat_session


async def get_session_detail(
    db: AsyncSession,
    owner_uuid: UUID,
    session_id: UUID,
) -> ChatSessionDetail:
    """Oturum detayını ve mesaj geçmişini döner. Başka kullanıcının oturumu ise 404."""
    await _verify_customer_exists(db, owner_uuid)

    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.owner_id == owner_uuid,
    )
    chat_session = await db.scalar(stmt)
    if chat_session is None:
        raise NotFoundError("Sohbet oturumu bulunamadı.")

    msgs_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = (await db.scalars(msgs_stmt)).all()

    return ChatSessionDetail(
        session=_to_session_out(chat_session),
        messages=[_to_message_out(m) for m in messages],
    )


async def list_chat_sessions(
    db: AsyncSession,
    owner_uuid: UUID,
) -> list[ChatSessionOut]:
    """Kullanıcının tüm sohbet oturumlarını son mesaj tarihine göre azalan sırada döner."""
    await _verify_customer_exists(db, owner_uuid)

    stmt = (
        select(ChatSession)
        .where(ChatSession.owner_id == owner_uuid)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = (await db.scalars(stmt)).all()
    return [_to_session_out(s) for s in sessions]


async def execute_chat_turn(
    db: AsyncSession,
    owner_id: str,
    question: str,
    session_id: UUID | None = None,
    *,
    llm: AssistantLLM | None = None,
) -> tuple[ChatSession, ChatMessage, ChatMessage, AssistantAnswer]:
    """Soruyu ve cevabı üretip veritabanına kaydeder."""
    clean_q = question.strip()
    if not clean_q:
        raise AppError("Soru boş olamaz.")

    try:
        owner_uuid = UUID(owner_id.strip())
    except (ValueError, AttributeError):
        raise AppError("Geçersiz kullanıcı kimliği.") from None

    chat_session = await get_or_create_session(db, owner_uuid, session_id, clean_q)

    # 1. Kullanıcı sorusunu kaydet
    user_msg = ChatMessage(
        id=uuid4(),
        session_id=chat_session.id,
        role="user",
        content=clean_q,
        question_type=None,
        sources=[],
        found=True,
        created_at=datetime.now(UTC),
    )
    db.add(user_msg)
    chat_session.updated_at = datetime.now(UTC)
    await db.flush()

    # 2. Asistan cevabını üret
    try:
        req = AssistantRequest(question=clean_q, owner_id=str(owner_uuid))
        answer = await answer_question(req, llm=llm, session=db)
    except (AssistantLLMError, LLMNotConfiguredError):
        # LLM erişilemezse arayüz kesilmesin: nazik bir mesaj kaydedilir, ayrıntı yalnızca logda.
        log.warning("assistant.llm_unavailable", session_id=str(chat_session.id))
        answer = AssistantAnswer(
            answer=ASSISTANT_UNAVAILABLE_MESSAGE,
            question_type=QuestionType.GECMIS_ONERI,
            sources=[],
            found=False,
        )

    # 3. Asistan cevabını kaydet
    assistant_msg = ChatMessage(
        id=uuid4(),
        session_id=chat_session.id,
        role="assistant",
        content=answer.answer,
        question_type=answer.question_type.value,
        sources=[s.model_dump(mode="json") for s in answer.sources],
        found=answer.found,
        created_at=datetime.now(UTC),
    )
    db.add(assistant_msg)
    chat_session.updated_at = datetime.now(UTC)
    await db.commit()

    return chat_session, user_msg, assistant_msg, answer


async def execute_chat_reply(
    db: AsyncSession,
    owner_id: str,
    question: str,
    session_id: UUID | None = None,
    *,
    llm: AssistantLLM | None = None,
) -> ChatReply:
    """Senkron yanıt döner (`POST /chat/messages`)."""
    chat_session, user_msg, assistant_msg, _ = await execute_chat_turn(
        db, owner_id, question, session_id, llm=llm
    )
    return ChatReply(
        session_id=chat_session.id,
        question=_to_message_out(user_msg),
        answer=_to_message_out(assistant_msg),
    )


async def stream_assistant_chat(
    db: AsyncSession,
    owner_id: str,
    question: str,
    session_id: UUID | None = None,
    *,
    request_id: str | None = None,
    llm: AssistantLLM | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """Issue #28 sözleşmesine uygun SSE akışı: `token` -> `sources` -> `done`."""
    try:
        chat_session, user_msg, assistant_msg, answer = await execute_chat_turn(
            db, owner_id, question, session_id, llm=llm
        )
    except AppError as err:
        yield ServerSentEvent(
            event="error",
            data=json.dumps(
                {
                    "type": "error",
                    "code": err.code,
                    "message": err.message,
                    "request_id": request_id,
                }
            ),
        )
        return
    except Exception:
        log.exception("assistant.chat_failed", request_id=request_id)
        yield ServerSentEvent(
            event="error",
            data=json.dumps(
                {
                    "type": "error",
                    "code": "internal_error",
                    "message": GENERIC_ERROR_MESSAGE,
                    "request_id": request_id,
                }
            ),
        )
        return

    # 1. token parçaları
    for chunk in _chunk_text(answer.answer):
        await asyncio.sleep(STREAM_CHUNK_DELAY_S)
        yield ServerSentEvent(
            event="token",
            data=json.dumps({"token": chunk, "text": chunk}),
        )

    # 2. sources
    yield ServerSentEvent(
        event="sources",
        data=json.dumps([s.model_dump(mode="json") for s in answer.sources]),
    )

    # 3. done
    yield ServerSentEvent(
        event="done",
        data=json.dumps(
            {
                "session_id": str(chat_session.id),
                "question": _to_message_out(user_msg).model_dump(mode="json"),
                "answer": _to_message_out(assistant_msg).model_dump(mode="json"),
            }
        ),
    )


async def stream_chat_messages(
    db: AsyncSession,
    owner_id: str,
    question: str,
    session_id: UUID | None = None,
    *,
    request_id: str | None = None,
    llm: AssistantLLM | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """docs/api.md ve frontend/mocks uyumlu SSE akışı: `status` -> `delta` -> `done`."""
    # 1. status: aranıyor
    yield ServerSentEvent(
        event="status",
        data=json.dumps({"type": "status", "stage": "araniyor"}),
    )

    try:
        chat_session, user_msg, assistant_msg, answer = await execute_chat_turn(
            db, owner_id, question, session_id, llm=llm
        )
    except AppError as err:
        yield ServerSentEvent(
            event="error",
            data=json.dumps(
                {
                    "type": "error",
                    "code": err.code,
                    "message": err.message,
                    "request_id": request_id,
                }
            ),
        )
        return
    except Exception:
        log.exception("assistant.chat_failed", request_id=request_id)
        yield ServerSentEvent(
            event="error",
            data=json.dumps(
                {
                    "type": "error",
                    "code": "internal_error",
                    "message": GENERIC_ERROR_MESSAGE,
                    "request_id": request_id,
                }
            ),
        )
        return

    # 2. status: doğrulanıyor
    yield ServerSentEvent(
        event="status",
        data=json.dumps({"type": "status", "stage": "dogrulaniyor"}),
    )

    # 3. delta parçaları
    for chunk in _chunk_text(answer.answer):
        await asyncio.sleep(STREAM_CHUNK_DELAY_S)
        yield ServerSentEvent(
            event="delta",
            data=json.dumps({"type": "delta", "text": chunk}),
        )

    # 4. done
    reply = ChatReply(
        session_id=chat_session.id,
        question=_to_message_out(user_msg),
        answer=_to_message_out(assistant_msg),
    )
    yield ServerSentEvent(
        event="done",
        data=json.dumps({"type": "done", "reply": reply.model_dump(mode="json")}),
    )

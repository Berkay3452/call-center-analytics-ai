"""Miço AI Asistan sohbet uç noktaları (#28).

Uçlar:
- `POST /api/v1/assistant/chat`: Asistan ile akışlı sohbet (SSE: token -> sources -> done)
- `GET /api/v1/assistant/sessions/{id}`: Belirtilen oturumun mesaj geçmişi (yalnızca sahibi)
- `GET /api/v1/assistant/sessions`: Kullanıcının tüm oturumları
- OpenAPI/Docs uyumluluğu için `/chat/...` uçları.
"""

from uuid import UUID

from fastapi import APIRouter, Request, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import OwnerIdDep, SessionDep
from app.schemas.api import (
    ChatQuestion,
    ChatReply,
    ChatSessionDetail,
    ChatSessionOut,
)
from app.services import assistant_chat

router = APIRouter(tags=["Miço AI Asistan"])


# --- Issue #28 Ana Uçları ---


@router.post(
    "/assistant/chat",
    summary="Miço AI asistana soru gönder (SSE akışı: token -> sources -> done)",
    response_description="Server-Sent Events akışı",
)
async def assistant_chat_stream(
    body: ChatQuestion,
    owner_id: OwnerIdDep,
    db: SessionDep,
    request: Request,
) -> EventSourceResponse:
    request_id = getattr(request.state, "request_id", None)
    generator = assistant_chat.stream_assistant_chat(
        db, owner_id, body.question, body.session_id, request_id=request_id
    )
    return EventSourceResponse(generator)


@router.get(
    "/assistant/sessions/{id}",
    summary="Asistan sohbet oturumu detayı ve geçmişi",
    response_model=ChatSessionDetail,
)
async def get_assistant_session_detail(
    id: UUID,
    owner_id: OwnerIdDep,
    db: SessionDep,
) -> ChatSessionDetail:
    return await assistant_chat.get_session_detail(db, UUID(owner_id), id)


@router.get(
    "/assistant/sessions",
    summary="Kullanıcının sohbet oturumları listesi",
    response_model=list[ChatSessionOut],
)
async def list_assistant_sessions(
    owner_id: OwnerIdDep,
    db: SessionDep,
) -> list[ChatSessionOut]:
    return await assistant_chat.list_chat_sessions(db, UUID(owner_id))


# --- docs/api.md ve frontend/openapi.json Uyumlu Uçlar ---


@router.post(
    "/chat/messages/stream",
    summary="Miço AI asistana soru gönder (SSE akışı: status -> delta -> done)",
    response_description="Server-Sent Events akışı",
)
async def chat_messages_stream(
    body: ChatQuestion,
    owner_id: OwnerIdDep,
    db: SessionDep,
    request: Request,
) -> EventSourceResponse:
    request_id = getattr(request.state, "request_id", None)
    generator = assistant_chat.stream_chat_messages(
        db, owner_id, body.question, body.session_id, request_id=request_id
    )
    return EventSourceResponse(generator)


@router.post(
    "/chat/messages",
    summary="Miço AI asistana soru gönder (senkron yanıt)",
    response_model=ChatReply,
    status_code=status.HTTP_200_OK,
)
async def chat_messages_sync(
    body: ChatQuestion,
    owner_id: OwnerIdDep,
    db: SessionDep,
) -> ChatReply:
    return await assistant_chat.execute_chat_reply(db, owner_id, body.question, body.session_id)


@router.get(
    "/chat/sessions/{session_id}",
    summary="Sohbet oturumu detayı ve mesaj geçmişi",
    response_model=ChatSessionDetail,
)
async def get_chat_session_detail(
    session_id: UUID,
    owner_id: OwnerIdDep,
    db: SessionDep,
) -> ChatSessionDetail:
    return await assistant_chat.get_session_detail(db, UUID(owner_id), session_id)


@router.get(
    "/chat/sessions",
    summary="Kullanıcının sohbet oturumları listesi",
    response_model=list[ChatSessionOut],
)
async def list_chat_sessions(
    owner_id: OwnerIdDep,
    db: SessionDep,
) -> list[ChatSessionOut]:
    return await assistant_chat.list_chat_sessions(db, UUID(owner_id))

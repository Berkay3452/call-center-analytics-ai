"""Çağrı okuma uçları (#51): sayfalı liste ve tekil çağrı detayı.

Sözleşme: docs/api.md.
"""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import AdminCallerDep, AudioStorageDep, RedisDep, SessionDep
from app.domain.audit import AuditAction
from app.schemas.api import CallDetail, CallFilters, CallListItem, CallMatchIn
from app.schemas.common import ErrorResponse, Page
from app.services import audio_ingest, call_deletion, call_matching, call_reader, transcript_live
from app.services.audit import has_recent_audit_event, record_audit_event

router = APIRouter(prefix="/calls", tags=["calls"])

# Aynı (çağrı, eylemi yapan, IP) için ses erişimi kaydı en çok bu aralıkla tekrarlanır.
AUDIO_AUDIT_WINDOW_S = 300
LIVE_AUDIT_WINDOW_S = 300  # canlı transkript izleme kaydı (yeniden bağlanmalar tekrar yazmaz)


@router.get(
    "",
    response_model=Page[CallListItem],
    summary="Çağrı listesi",
    operation_id="listCalls",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def list_calls(
    _: AdminCallerDep,
    session: SessionDep,
    filters: Annotated[CallFilters, Query()],
) -> Page[CallListItem]:
    """Filtrelere göre sayfalı çağrı listesi döndürür."""
    return await call_reader.list_calls(session, filters)


@router.get(
    "/{call_id}",
    response_model=CallDetail,
    summary="Çağrı detayı",
    operation_id="getCallById",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_call(
    call_id: UUID,
    _: AdminCallerDep,
    session: SessionDep,
) -> CallDetail:
    """Belirli bir çağrının tüm santral, transkript ve analiz verilerini getirir."""
    return await call_reader.get_call_detail(session, call_id)


@router.delete(
    "/{call_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Çağrıyı ve ses kaydını sil (KVKK)",
    operation_id="deleteCall",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def delete_call(
    call_id: UUID,
    caller: AdminCallerDep,
    session: SessionDep,
    storage: AudioStorageDep,
) -> Response:
    """Çağrıyı, ses dosyasını, transkripti (ham ve maskeli), analizi ve CRM önerilerini siler.

    Yalnızca yönetici bağlamı (`X-User-Id` yok; tekne sahibi kimliği 403). Servis emirleri
    silinmez, çağrıyla bağı (`source_call_id`) kopar. İşlenmekte olan çağrı 409 alır. Silme olayı
    denetim günlüğüne kişisel veri olmadan yazılır (#269).
    """
    await call_deletion.delete_call(session, storage, call_id, actor=caller)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{call_id}/match",
    response_model=CallDetail,
    summary="Çağrıyı müşteri ve tekneye elle eşleştir",
    operation_id="matchCall",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def match_call_endpoint(
    call_id: UUID,
    payload: CallMatchIn,
    caller: AdminCallerDep,
    session: SessionDep,
) -> CallDetail:
    """Eşleşmeyen veya yanlış bağlanan çağrıyı belirli bir müşteri ve tekneye bağlar (#119)."""
    async with session.begin():
        detail = await call_matching.manual_match_call(
            session, call_id, payload.customer_id, payload.boat_id
        )
        await record_audit_event(
            session,
            action=AuditAction.CAGRI_ESLESTIRILDI,
            actor=caller,
            target_type="call",
            target_id=call_id,
            details={"musteri_id": payload.customer_id, "tekne_id": payload.boat_id},
        )
        return detail


@router.get(
    "/{call_id}/audio",
    summary="Çağrı ses kaydı",
    operation_id="getCallAudio",
    responses={
        200: {
            "description": "Ses dosyası akışı (Range destekli, 200 veya 206)",
            "content": {
                "audio/wav": {},
                "audio/mpeg": {},
                "audio/mp4": {},
                "audio/ogg": {},
                "audio/flac": {},
                "audio/aac": {},
                "audio/webm": {},
            },
        },
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_call_audio(
    call_id: UUID,
    request: Request,
    caller: AdminCallerDep,
    session: SessionDep,
    storage: AudioStorageDep,
) -> Response:
    """Çağrıya ait ses dosyasını akıtır (Range isteklerini destekler).

    Yalnızca yönetici bağlamı (`X-User-Id` yok): çağrı kayıtları işletmenin içidir, tekne sahibi
    kimliğiyle gelen istek 403 alır (#270).

    Erişim denetim günlüğüne yazılır (#267). Oynatıcılar çok sayıda Range isteği attığı için her
    istek değil, (çağrı, eylemi yapan, IP) başına her
    `AUDIO_AUDIT_WINDOW_S` saniyede en az bir kayıt düşer;
    başlangıç ofseti (`bytes=1-` gibi) kaydı atlatamaz.
    """
    range_header = request.headers.get("range")
    response = await audio_ingest.get_call_audio_response(
        session, call_id, storage, range_header=range_header
    )
    if not await has_recent_audit_event(
        session,
        action=AuditAction.SES_ERISIMI,
        actor=caller,
        target_type="call",
        target_id=call_id,
        within_s=AUDIO_AUDIT_WINDOW_S,
    ):
        await record_audit_event(
            session,
            action=AuditAction.SES_ERISIMI,
            actor=caller,
            target_type="call",
            target_id=call_id,
        )
        await session.commit()
    return response


@router.get(
    "/{call_id}/transcript/stream",
    summary="Canlı transkript akışı (SSE)",
    operation_id="streamCallTranscript",
    response_description="Server-Sent Events: segment ... sonra done | error | timeout",
    responses={
        200: {"description": "SSE akışı", "content": {"text/event-stream": {}}},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def stream_call_transcript(
    call_id: UUID,
    request: Request,
    caller: AdminCallerDep,
    redis: RedisDep,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Yazıya çevirme sürerken konuşma parçalarını canlı iletir (#324).

    Yalnızca yönetici bağlamı: akış **ham** transkripttir (tekne sahibi kimliği 403). Olaylar:
    `segment` (`seq`, `speaker`, `start_ms`, `end_ms`, `text`), `done`, `error` (yalnız sabit
    kod), `timeout`. `Last-Event-ID` ile kaldığı yerden devam edilir. İzleme, (çağrı, eylemi
    yapan, IP) başına her `LIVE_AUDIT_WINDOW_S` saniyede bir denetim günlüğüne yazılır.
    """
    factory = request.app.state.session_factory
    await transcript_live.call_state(factory, call_id)  # yoksa 404
    await transcript_live.acquire_connection(redis, call_id)
    try:
        async with factory() as audit_session:
            if not await has_recent_audit_event(
                audit_session,
                action=AuditAction.CANLI_TRANSKRIPT_IZLENDI,
                actor=caller,
                target_type="call",
                target_id=call_id,
                within_s=LIVE_AUDIT_WINDOW_S,
            ):
                await record_audit_event(
                    audit_session,
                    action=AuditAction.CANLI_TRANSKRIPT_IZLENDI,
                    actor=caller,
                    target_type="call",
                    target_id=call_id,
                )
                await audit_session.commit()
    except BaseException:
        await transcript_live.release_connection(redis, call_id)
        raise

    async def events() -> AsyncIterator[ServerSentEvent]:
        try:
            async for event in transcript_live.stream_transcript(
                redis, factory, call_id, last_event_id=last_event_id
            ):
                yield event
        finally:
            await transcript_live.release_connection(redis, call_id)

    return EventSourceResponse(
        events(),
        ping=15,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )

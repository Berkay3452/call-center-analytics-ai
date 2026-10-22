"""Çağrı okuma uçları (#51): sayfalı liste ve tekil çağrı detayı.

Sözleşme: docs/api.md.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import AudioStorageDep, ServiceCallerDep, SessionDep
from app.schemas.api import CallDetail, CallFilters, CallListItem, CallMatchIn
from app.schemas.common import ErrorResponse, Page
from app.services import audio_ingest, call_matching, call_reader

router = APIRouter(prefix="/calls", tags=["calls"])


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
    _: ServiceCallerDep,
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
    _: ServiceCallerDep,
    session: SessionDep,
) -> CallDetail:
    """Belirli bir çağrının tüm santral, transkript ve analiz verilerini getirir."""
    return await call_reader.get_call_detail(session, call_id)


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
    _: ServiceCallerDep,
    session: SessionDep,
) -> CallDetail:
    """Eşleşmeyen veya yanlış bağlanan çağrıyı belirli bir müşteri ve tekneye bağlar (#119)."""
    async with session.begin():
        return await call_matching.manual_match_call(
            session, call_id, payload.customer_id, payload.boat_id
        )


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
        404: {"model": ErrorResponse},
    },
)
async def get_call_audio(
    call_id: UUID,
    request: Request,
    _: ServiceCallerDep,
    session: SessionDep,
    storage: AudioStorageDep,
) -> Response:
    """Çağrıya ait ses dosyasını akıtır (Range isteklerini destekler)."""
    range_header = request.headers.get("range")
    return await audio_ingest.get_call_audio_response(
        session, call_id, storage, range_header=range_header
    )

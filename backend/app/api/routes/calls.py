"""Çağrı okuma uçları (#51): sayfalı liste ve tekil çağrı detayı.

Sözleşme: docs/api.md.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import ServiceCallerDep, SessionDep, SettingsDep
from app.schemas.api import CallDetail, CallFilters, CallListItem
from app.schemas.common import ErrorResponse, Page
from app.services import audio_ingest, call_reader

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
    _: ServiceCallerDep,
    session: SessionDep,
    settings: SettingsDep,
) -> FileResponse:
    """Çağrıya ait ses dosyasını akıtır (Range isteklerini destekler)."""
    file_path, media_type = await audio_ingest.get_call_audio_file(session, call_id, settings)
    return FileResponse(file_path, media_type=media_type)

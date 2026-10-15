"""Çağrı ve CRM okuma uçlarının HTTP davranışı (#51).

Yetkilendirme (X-Service-Key), sayfalama/filtre parametreleri ve hata yanıtları.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.api.deps import get_db_session
from app.api.routes import calls, crm
from app.core.errors import NotFoundError
from app.domain.enums import CallType, RequestCategory, Urgency
from app.main import create_app
from app.schemas.api import (
    CallDetail,
    CallFilters,
    CallListItem,
    CrmRecordItem,
    TranscriptOut,
    TranscriptSegmentOut,
)
from app.schemas.common import Page
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}
CALL_ID = UUID("11111111-1111-4111-8111-111111111111")


class DummySession:
    """Sahte DB oturumu."""

    pass


class CallReaderSpy:
    """call_reader servisinin sahte uygulaması."""

    def __init__(self) -> None:
        self.last_call_filters: CallFilters | None = None
        self.last_crm_filters: CallFilters | None = None
        self.call_detail_target_id: UUID | None = None

    async def list_calls(self, session: Any, filters: CallFilters) -> Page[CallListItem]:
        self.last_call_filters = filters
        items = [
            CallListItem(
                id=CALL_ID,
                started_at=datetime(2026, 10, 12, 9, 5, tzinfo=UTC),
                duration_s=184,
                answer_delay_s=12,
                switchboard_outcome="geri_aranacak",
                customer_name="Burak Çelik",
                boat_name="Rüzgar",
                marina="Tuzla Marina",
                state="tamam",
                call_type=CallType.SERVIS,
                request_category=RequestCategory.MAKINE,
                urgency=Urgency.YUKSEK,
                sales_outcome=None,
                summary="Motor devir almıyor.",
            )
        ]
        return Page[CallListItem](
            items=items, total=1, page=filters.page, page_size=filters.page_size
        )

    async def get_call_detail(self, session: Any, call_id: UUID) -> CallDetail:
        self.call_detail_target_id = call_id
        if call_id != CALL_ID:
            raise NotFoundError("Çağrı bulunamadı.")
        return CallDetail(
            id=CALL_ID,
            started_at=datetime(2026, 10, 12, 9, 5, tzinfo=UTC),
            duration_s=184,
            answer_delay_s=12,
            switchboard_outcome="geri_aranacak",
            customer_name="Burak Çelik",
            boat_name="Rüzgar",
            marina="Tuzla Marina",
            has_audio=True,
            state="tamam",
            transcript=TranscriptOut(
                text="Temsilci: Miço Usta\nMüşteri: Motor arızası",
                segments=[
                    TranscriptSegmentOut(
                        index=0,
                        speaker="rep",
                        start_ms=0,
                        end_ms=2000,
                        text="Miço Usta",
                    )
                ],
            ),
            analysis=None,
        )

    async def list_crm_records(self, session: Any, filters: CallFilters) -> Page[CrmRecordItem]:
        self.last_crm_filters = filters
        items = [
            CrmRecordItem(
                call_id=CALL_ID,
                started_at=datetime(2026, 10, 12, 9, 5, tzinfo=UTC),
                customer_name="Burak Çelik",
                boat_name="Rüzgar",
                analysis_version=1,
                request_category=RequestCategory.MAKINE,
                location="Tuzla Marina",
                problem="Motor devir almıyor",
                urgency=Urgency.YUKSEK,
                potential_job="Arıza tespiti",
                next_action=None,
                evidence={"problem": "devir almıyor"},
            )
        ]
        return Page[CrmRecordItem](
            items=items, total=1, page=filters.page, page_size=filters.page_size
        )


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> CallReaderSpy:
    spy = CallReaderSpy()
    monkeypatch.setattr(calls.call_reader, "list_calls", spy.list_calls)
    monkeypatch.setattr(calls.call_reader, "get_call_detail", spy.get_call_detail)
    monkeypatch.setattr(crm.call_reader, "list_crm_records", spy.list_crm_records)
    return spy


@pytest.fixture
async def authed_client(spy: CallReaderSpy) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())

    async def fake_session() -> AsyncIterator[DummySession]:
        yield DummySession()

    app.dependency_overrides[get_db_session] = fake_session
    async for c in _client_for(app):
        yield c


@pytest.mark.parametrize("path", ["/api/v1/calls", f"/api/v1/calls/{CALL_ID}", "/api/v1/crm"])
async def test_read_endpoints_require_service_key(
    authed_client: httpx.AsyncClient, path: str
) -> None:
    # Anahtarsız istek -> 401
    resp = await authed_client.get(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"

    # Yanlış anahtar -> 401
    resp_wrong = await authed_client.get(path, headers={"X-Service-Key": "gecersiz"})
    assert resp_wrong.status_code == 401
    assert resp_wrong.json()["error"]["code"] == "unauthorized"


async def test_list_calls_returns_paginated_list(
    authed_client: httpx.AsyncClient, spy: CallReaderSpy
) -> None:
    resp = await authed_client.get("/api/v1/calls", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(CALL_ID)
    assert body["items"][0]["customer_name"] == "Burak Çelik"
    assert body["items"][0]["call_type"] == "servis"


async def test_list_calls_forwards_filter_parameters(
    authed_client: httpx.AsyncClient, spy: CallReaderSpy
) -> None:
    resp = await authed_client.get(
        "/api/v1/calls?page=2&page_size=10&call_type=servis&urgency=yuksek&q=Burak",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert spy.last_call_filters is not None
    assert spy.last_call_filters.page == 2
    assert spy.last_call_filters.page_size == 10
    assert spy.last_call_filters.call_type == CallType.SERVIS
    assert spy.last_call_filters.urgency == Urgency.YUKSEK
    assert spy.last_call_filters.q == "Burak"


async def test_get_call_detail_returns_call(
    authed_client: httpx.AsyncClient, spy: CallReaderSpy
) -> None:
    resp = await authed_client.get(f"/api/v1/calls/{CALL_ID}", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(CALL_ID)
    assert body["customer_name"] == "Burak Çelik"
    assert body["has_audio"] is True
    assert body["transcript"]["segments"][0]["text"] == "Miço Usta"


async def test_get_call_detail_not_found(
    authed_client: httpx.AsyncClient, spy: CallReaderSpy
) -> None:
    unknown_id = uuid4()
    resp = await authed_client.get(f"/api/v1/calls/{unknown_id}", headers=HEADERS)
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "Çağrı bulunamadı."


async def test_list_crm_records_returns_paginated_list(
    authed_client: httpx.AsyncClient, spy: CallReaderSpy
) -> None:
    resp = await authed_client.get("/api/v1/crm", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["call_id"] == str(CALL_ID)
    assert item["analysis_version"] == 1
    assert item["request_category"] == "makine"
    assert item["problem"] == "Motor devir almıyor"


async def test_filters_reject_invalid_date_range(authed_client: httpx.AsyncClient) -> None:
    resp = await authed_client.get(
        "/api/v1/calls?date_from=2026-10-15&date_to=2026-10-10",
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_filters_reject_oversized_page_size(authed_client: httpx.AsyncClient) -> None:
    resp = await authed_client.get("/api/v1/calls?page_size=200", headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_openapi_schema_includes_read_endpoints() -> None:
    app = create_app(make_settings())
    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/calls" in paths
    assert "get" in paths["/api/v1/calls"]
    assert paths["/api/v1/calls"]["get"]["operationId"] == "listCalls"

    assert "/api/v1/calls/{call_id}" in paths
    assert "get" in paths["/api/v1/calls/{call_id}"]
    assert paths["/api/v1/calls/{call_id}"]["get"]["operationId"] == "getCallById"

    assert "/api/v1/calls/{call_id}/audio" in paths
    assert "get" in paths["/api/v1/calls/{call_id}/audio"]
    assert paths["/api/v1/calls/{call_id}/audio"]["get"]["operationId"] == "getCallAudio"

    assert "/api/v1/crm" in paths
    assert "get" in paths["/api/v1/crm"]
    assert paths["/api/v1/crm"]["get"]["operationId"] == "listCrmRecords"


async def test_list_calls_and_crm_forward_marina_parameter(
    authed_client: httpx.AsyncClient, spy: CallReaderSpy
) -> None:
    resp_calls = await authed_client.get("/api/v1/calls?marina=Tuzla+Marina", headers=HEADERS)
    assert resp_calls.status_code == 200
    assert spy.last_call_filters is not None
    assert spy.last_call_filters.marina == "Tuzla Marina"

    resp_crm = await authed_client.get("/api/v1/crm?marina=Tuzla+Marina", headers=HEADERS)
    assert resp_crm.status_code == 200
    assert spy.last_crm_filters is not None
    assert spy.last_crm_filters.marina == "Tuzla Marina"

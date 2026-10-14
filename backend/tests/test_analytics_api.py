"""KPI ve çağrı analitiği ucu HTTP testleri (#52).

Yetkilendirme (X-Service-Key), sorgu parametreleri, hata yönetimi ve OpenAPI sözleşmesi.
"""

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest

from app.api.deps import get_db_session
from app.api.routes import analytics
from app.domain.enums import LossReason, RequestCategory, Urgency
from app.main import create_app
from app.schemas.analysis import CountItem, DailyCount, KpiSummary
from app.schemas.api import PeriodFilter
from tests.conftest import TEST_SERVICE_KEY, _client_for, make_settings

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


class DummySession:
    """Sahte DB oturumu."""

    pass


class AnalyticsSpy:
    """analytics_service sahte uygulaması."""

    def __init__(self) -> None:
        self.last_filter: PeriodFilter | None = None

    async def get_kpi_summary(self, session: Any, filter_params: PeriodFilter) -> KpiSummary:
        self.last_filter = filter_params
        return KpiSummary(
            period_start=filter_params.date_from or date(2026, 10, 6),
            period_end=filter_params.date_to or date(2026, 10, 12),
            total_calls=30,
            analyzed_calls=28,
            new_customers=4,
            service_requests=13,
            quote_requests=6,
            urgent_requests=3,
            converted_sales=11,
            conversion_rate=0.393,
            lost_by_reason={LossReason.FIYAT: 4, LossReason.GEC_DONUS: 2},
            top_problems=[CountItem(name="Motor devir sorunu", count=5)],
            busiest_marinas=[CountItem(name="Tuzla Marina", count=9)],
            by_category={RequestCategory.MAKINE: 11},
            by_urgency={Urgency.YUKSEK: 9},
            daily_calls=[
                DailyCount(day=date(2026, 10, 6), count=4),
                DailyCount(day=date(2026, 10, 7), count=6),
            ],
            avg_answer_delay_s=14.5,
        )


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> AnalyticsSpy:
    spy = AnalyticsSpy()
    monkeypatch.setattr(analytics.analytics_service, "get_kpi_summary", spy.get_kpi_summary)
    return spy


@pytest.fixture
async def authed_client(spy: AnalyticsSpy) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())

    async def fake_session() -> AsyncIterator[DummySession]:
        yield DummySession()

    app.dependency_overrides[get_db_session] = fake_session
    async for c in _client_for(app):
        yield c


async def test_summary_requires_service_key(authed_client: httpx.AsyncClient) -> None:
    # Anahtarsız istek -> 401
    resp = await authed_client.get("/api/v1/analytics/summary")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"

    # Yanlış anahtar -> 401
    resp_wrong = await authed_client.get(
        "/api/v1/analytics/summary", headers={"X-Service-Key": "gecersiz"}
    )
    assert resp_wrong.status_code == 401
    assert resp_wrong.json()["error"]["code"] == "unauthorized"


async def test_summary_returns_kpi_data(
    authed_client: httpx.AsyncClient, spy: AnalyticsSpy
) -> None:
    resp = await authed_client.get("/api/v1/analytics/summary", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 30
    assert body["analyzed_calls"] == 28
    assert body["converted_sales"] == 11
    assert body["conversion_rate"] == 0.393
    assert body["lost_by_reason"]["fiyat"] == 4
    assert body["by_category"]["makine"] == 11
    assert body["avg_answer_delay_s"] == 14.5


async def test_summary_forwards_filter_dates(
    authed_client: httpx.AsyncClient, spy: AnalyticsSpy
) -> None:
    resp = await authed_client.get(
        "/api/v1/analytics/summary?date_from=2026-10-01&date_to=2026-10-10",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert spy.last_filter is not None
    assert spy.last_filter.date_from == date(2026, 10, 1)
    assert spy.last_filter.date_to == date(2026, 10, 10)


async def test_summary_rejects_invalid_date_order(authed_client: httpx.AsyncClient) -> None:
    resp = await authed_client.get(
        "/api/v1/analytics/summary?date_from=2026-10-15&date_to=2026-10-10",
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_openapi_schema_includes_analytics_summary() -> None:
    app = create_app(make_settings())
    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/analytics/summary" in paths
    assert "get" in paths["/api/v1/analytics/summary"]
    endpoint = paths["/api/v1/analytics/summary"]["get"]
    assert endpoint["operationId"] == "getKpiSummary"
    assert endpoint["summary"] == "KPI ve analitik özeti"

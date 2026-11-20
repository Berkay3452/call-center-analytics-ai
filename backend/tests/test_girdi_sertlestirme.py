"""Kara kutu QA turunun (#320, #338) bulduğu 500'lerin regresyon testleri.

Bulgu: NUL karakteri, sınır dışı tarih ve `int4` taşması şema katmanında yakalanmayınca
PostgreSQL hatası 500 olarak dönüyordu. Burada hata sunucusuz, şema ve işleyici düzeyinde
sabitlenir.
"""

from datetime import UTC, date, datetime

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError

from app.core.errors import is_bad_input_db_error, register_exception_handlers
from app.schemas.api import (
    AudioCallMeta,
    CallCreate,
    CallFilters,
    ChatQuestion,
    CrmApproveIn,
    PeriodFilter,
    ServiceOrderFilters,
)
from app.schemas.assistant import AssistantRequest
from app.schemas.audit import AuditLogFilters

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize("model", [CallFilters, PeriodFilter, ServiceOrderFilters])
@pytest.mark.parametrize("field", ["date_from", "date_to"])
@pytest.mark.parametrize("value", [date(1, 1, 1), date(9999, 12, 31), date(1999, 12, 31)])
def test_filter_dates_outside_sane_range_are_rejected(model: type, field: str, value: date) -> None:
    with pytest.raises(ValidationError):
        model(**{field: value})


def test_filter_dates_inside_range_are_accepted() -> None:
    assert CallFilters(date_from=date(2026, 11, 1), date_to=date(2026, 11, 30)).date_to


@pytest.mark.parametrize("field", ["q", "marina"])
def test_filter_text_rejects_nul(field: str) -> None:
    with pytest.raises(ValidationError):
        CallFilters(**{field: "a\x00b"})


def test_audit_range_rejects_extreme_years() -> None:
    with pytest.raises(ValidationError):
        AuditLogFilters(since=datetime(9999, 12, 31, tzinfo=UTC))
    assert AuditLogFilters(since=NOW).since == NOW


@pytest.mark.parametrize(
    "extra",
    [
        {"customer_name": "a\x00"},
        {"marina": "a\x00"},
        {"customer_name": "A" * 201},
        {"duration_s": 540966033835368279617652654080},
        {"answer_delay_s": 2**31},
        {"started_at": datetime(1, 1, 1, tzinfo=UTC)},
        {"transcript": "a\x00b"},
    ],
)
def test_call_create_rejects_database_breaking_values(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CallCreate(**{"started_at": NOW, "transcript": "Müşteri: merhaba", **extra})


def test_call_create_segments_reject_nul_and_overflow() -> None:
    base = {"started_at": NOW}
    for seg in (
        {"speaker": "rep", "text": "a\x00"},
        {"speaker": "rep", "text": "x", "start_ms": 2**40},
    ):
        with pytest.raises(ValidationError):
            CallCreate(**base, segments=[seg])


def test_audio_meta_rejects_the_same_values() -> None:
    with pytest.raises(ValidationError):
        AudioCallMeta(started_at=NOW, customer_name="a\x00")
    with pytest.raises(ValidationError):
        AudioCallMeta(started_at=NOW, duration_s=10**30)


def test_valid_call_still_accepted() -> None:
    call = CallCreate(
        started_at=NOW, duration_s=7200, customer_name="Ahmet Yılmaz", transcript="Müşteri: Merhaba"
    )
    assert call.duration_s == 7200


@pytest.mark.parametrize("model", [ChatQuestion, AssistantRequest])
def test_questions_reject_nul(model: type) -> None:
    extra = {"owner_id": "x"} if model is AssistantRequest else {}
    with pytest.raises(ValidationError):
        model(question="a\x00b", **extra)
    assert model(question="Poyraz'ın aküsü ne zaman değişti?", **extra).question


def test_crm_notes_reject_nul() -> None:
    with pytest.raises(ValidationError):
        CrmApproveIn(note="a\x00")


# --- Veritabanı veri hatası -> 422 (güvenlik ağı) ------------------------------------------------


def _db_error(cause: BaseException) -> DBAPIError:
    orig = Exception("sürücü hatası")
    orig.__cause__ = cause
    return DBAPIError("SELECT 1", {}, orig)


def test_bad_input_database_errors_are_recognised() -> None:
    assert is_bad_input_db_error(_db_error(asyncpg.exceptions.DataError("değer taştı")))
    assert is_bad_input_db_error(
        _db_error(asyncpg.exceptions.CharacterNotInRepertoireError("0x00"))
    )
    assert not is_bad_input_db_error(_db_error(asyncpg.exceptions.UniqueViolationError("kopya")))
    assert not is_bad_input_db_error(_db_error(ConnectionError("bağlantı koptu")))


def _client(raise_error: BaseException) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise raise_error

    return TestClient(app, raise_server_exceptions=False)


def test_handler_returns_422_for_bad_input_and_500_otherwise() -> None:
    bad = _client(_db_error(asyncpg.exceptions.CharacterNotInRepertoireError("0x00"))).get("/boom")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"
    assert "0x00" not in bad.text  # değer yanıta sızmaz

    other = _client(_db_error(ConnectionError("db kapalı"))).get("/boom")
    assert other.status_code == 500
    assert other.json()["error"]["code"] == "internal_error"

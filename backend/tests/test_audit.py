"""Denetim günlüğü birim testleri (#267): veritabanı gerekmez; doğrulama ve kişisel veri kuralı."""

import re
import uuid
from pathlib import Path

import httpx
import pytest

from app.core.security import ServiceCaller
from app.domain.audit import AuditAction, AuditActorRole, AuditOutcome
from app.services.audit import (
    AuditDataError,
    actor_of,
    build_audit_event,
    sanitize_details,
)
from tests.conftest import TEST_SERVICE_KEY

OWNER = "11111111-1111-4111-8111-111111111111"


def test_event_accepts_ids_types_and_constants() -> None:
    ev = build_audit_event(
        action=AuditAction.CRM_ONAYLANDI,
        actor=ServiceCaller(owner_id=OWNER),
        target_type="call",
        target_id=uuid.UUID(OWNER),
        details={"kaynak": "ses", "boyut_bayt": 1024, "duzenlendi": True, "yok": None},
        request_id="abc123",
        ip="203.0.113.7",
    )
    assert ev.actor_id == uuid.UUID(OWNER)
    assert ev.actor_role == "tekne_sahibi"
    assert ev.action == "crm_onaylandi"
    assert ev.outcome == "basarili"
    assert ev.target_id == OWNER
    assert ev.details["boyut_bayt"] == 1024
    assert ev.ip == "203.0.113.7"


@pytest.mark.parametrize(
    "value",
    [
        "Ali Yılmaz",  # ad, boşluk
        "ali@example.com",  # e-posta
        "+90 532 123 45 67",  # telefon
        "05321234567",  # telefon (yalnız rakam)
        "12345678901",  # T.C. kimlik no biçimi
        "4111111111111111",  # kart no biçimi
        "Motor devir almıyor, acil yardım",  # serbest metin
        "a" * 65,  # çok uzun
        "",
    ],
)
def test_personal_data_like_values_are_rejected(value: str) -> None:
    with pytest.raises(AuditDataError):
        sanitize_details({"deger": value})
    with pytest.raises(AuditDataError):
        build_audit_event(action=AuditAction.SES_ERISIMI, target_id=value)


def test_details_shape_rules() -> None:
    with pytest.raises(AuditDataError):
        sanitize_details({"Kötü Anahtar": 1})
    with pytest.raises(AuditDataError):
        sanitize_details({"ic": {"x": 1}})
    with pytest.raises(AuditDataError):
        sanitize_details({"liste": ["a"]})
    with pytest.raises(AuditDataError):
        sanitize_details({f"k{i}": i for i in range(11)})
    assert sanitize_details(None) == {}


def test_actor_id_must_be_uuid_and_unknown_action_is_rejected() -> None:
    with pytest.raises(AuditDataError):
        build_audit_event(action=AuditAction.SES_ERISIMI, actor_id="ali")
    with pytest.raises(ValueError):
        build_audit_event(action="bilinmeyen_olay")  # type: ignore[arg-type]


def test_request_id_from_header_never_breaks_event() -> None:
    ev = build_audit_event(action=AuditAction.SES_ERISIMI, request_id="kötü başlık değeri!")
    assert ev.request_id is None
    assert build_audit_event(action=AuditAction.SES_ERISIMI, ip="degil-ip").ip is None


def test_actor_of_contexts() -> None:
    assert actor_of(None) == (None, AuditActorRole.SISTEM)
    assert actor_of(ServiceCaller()) == (None, AuditActorRole.SERVIS)
    assert actor_of(ServiceCaller(owner_id=OWNER)) == (
        uuid.UUID(OWNER),
        AuditActorRole.TEKNE_SAHIBI,
    )


def test_outcome_values_match_documented_check() -> None:
    assert {o.value for o in AuditOutcome} == {"basarili", "reddedildi", "hata"}


def test_audit_rows_are_only_built_by_the_audit_service() -> None:
    """`AuditLog(...)` yalnızca servis modülünde kurulur: tek giriş noktası doğrulamayı atlatmaz."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if p.name not in {"audit.py"} and re.search(r"\bAuditLog\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


async def test_list_endpoint_requires_service_key(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/audit-log")
    assert resp.status_code == 401


async def test_list_endpoint_rejects_owner_context(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/audit-log", headers={"X-Service-Key": TEST_SERVICE_KEY, "X-User-Id": OWNER}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_list_endpoint_validates_filters(client: httpx.AsyncClient) -> None:
    headers = {"X-Service-Key": TEST_SERVICE_KEY}
    assert (await client.get("/api/v1/audit-log?action=yok", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/audit-log?page_size=101", headers=headers)).status_code == 422
    bad_range = "/api/v1/audit-log?since=2026-11-02T00:00:00Z&until=2026-11-01T00:00:00Z"
    assert (await client.get(bad_range, headers=headers)).status_code == 422


def test_no_update_or_delete_endpoints_for_audit_log() -> None:
    from app.main import create_app
    from tests.conftest import make_settings

    paths = create_app(make_settings()).openapi()["paths"]
    methods = {m for path, ops in paths.items() if "audit" in path for m in ops}
    assert methods == {"get"}

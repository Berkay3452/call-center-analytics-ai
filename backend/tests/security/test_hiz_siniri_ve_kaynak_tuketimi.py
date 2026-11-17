"""Hız sınırı ve kaynak tüketimi saldırıları (OWASP API4, LLM10): sınırı atlatma denemeleri,
aşırı büyük gövde/alan, kimlik döndürme, sahte IP başlıkları.
"""

from uuid import uuid4

import pytest

from tests.conftest import TEST_SERVICE_KEY, make_settings
from tests.security.helpers import OWNER_A, client_for, owner_headers

KEY_HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


def limited_settings(**overrides: int) -> object:
    return make_settings(rate_limit_backend="memory", **overrides)


@pytest.mark.parametrize(
    "spoof",
    [
        pytest.param(lambda i: {"X-Forwarded-For": f"10.0.0.{i}"}, id="x-forwarded-for"),
        pytest.param(lambda i: {"X-Real-IP": f"10.1.0.{i}"}, id="x-real-ip"),
        pytest.param(lambda i: {"Forwarded": f"for=10.2.0.{i}"}, id="forwarded"),
        pytest.param(lambda i: {"CF-Connecting-IP": f"10.3.0.{i}"}, id="cf-connecting-ip"),
    ],
)
async def test_spoofed_ip_headers_do_not_reset_the_ip_ceiling(spoof: object) -> None:
    settings = limited_settings(rate_limit_general_per_min=1000, rate_limit_ip_general_per_min=10)
    async for c in client_for(settings):  # type: ignore[arg-type]
        codes = [
            (
                await c.get(
                    "/api/v1/me",
                    headers={**KEY_HEADERS, "X-User-Id": str(uuid4()), **spoof(i)},  # type: ignore[operator]
                )
            ).status_code
            for i in range(14)
        ]
        assert codes[:10] == [200] * 10
        assert set(codes[10:]) == {429}


async def test_rotating_user_ids_and_wrong_keys_cannot_dodge_auth_failure_limit() -> None:
    settings = limited_settings(rate_limit_auth_fail_per_min=4)
    async for c in client_for(settings):  # type: ignore[arg-type]
        codes = [
            (
                await c.get(
                    "/api/v1/me",
                    headers={"X-Service-Key": f"k{i}", "X-User-Id": str(uuid4())},
                )
            ).status_code
            for i in range(8)
        ]
        assert codes[:4] == [401] * 4
        assert set(codes[4:]) == {429}


async def test_429_response_is_cheap_and_leaks_nothing() -> None:
    settings = limited_settings(rate_limit_general_per_min=1, rate_limit_ip_general_per_min=1)
    async for c in client_for(settings):  # type: ignore[arg-type]
        await c.get("/api/v1/me", headers=KEY_HEADERS)
        resp = await c.get("/api/v1/me", headers=KEY_HEADERS)

        assert resp.status_code == 429
        assert TEST_SERVICE_KEY not in resp.text
        assert "Traceback" not in resp.text
        assert resp.headers["x-content-type-options"] == "nosniff"


async def test_oversized_json_is_rejected_before_parsing() -> None:
    async for c in client_for(make_settings(max_json_body_kb=8)):
        for payload in ('{"question": "' + "a" * 20_000 + '"}', "[" * 50_000, "{" * 50_000):
            resp = await c.post(
                "/api/v1/chat/messages",
                content=payload,
                headers={**owner_headers(OWNER_A), "Content-Type": "application/json"},
            )
            assert resp.status_code == 413, payload[:20]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"question": ""}, "bos soru"),
        ({"question": "a" * 5001}, "5000 karakter üstü soru"),
        ({"question": 12345}, "yanlış tür"),
        ({"question": ["a"]}, "liste"),
        ({"question": {"$ne": None}}, "nesne enjeksiyonu"),
        ({}, "soru yok"),
    ],
)
async def test_invalid_question_payloads_are_rejected_with_422(
    body: dict[str, object], reason: str
) -> None:
    async for c in client_for(make_settings(max_json_body_kb=64)):
        resp = await c.post("/api/v1/chat/messages", json=body, headers=owner_headers(OWNER_A))

        assert resp.status_code == 422, reason
        assert "Traceback" not in resp.text


async def test_malformed_json_gives_clean_client_error() -> None:
    async for c in client_for(make_settings()):
        resp = await c.post(
            "/api/v1/chat/messages",
            content=b'{"question": ',
            headers={**owner_headers(OWNER_A), "Content-Type": "application/json"},
        )

        assert resp.status_code in {400, 422}
        assert "Traceback" not in resp.text and "JSONDecodeError" not in resp.text

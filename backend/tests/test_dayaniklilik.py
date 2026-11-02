"""Dayanıklılık ölçüm betiğinin (scripts/dayaniklilik.py) yardımcıları; ağ/LLM/veritabanı yok."""

import httpx
import pytest

from scripts.dayaniklilik import (
    CallRun,
    FakeLLM,
    percentile,
    scenarios,
    stage_seconds,
    summarize_batch,
    synthetic_ids,
)


def agent_run(agent: str, ms: int, **over: object) -> dict[str, object]:
    return {
        "agent": agent,
        "latency_ms": ms,
        "attempts": 1,
        "tokens_in": 10,
        "tokens_out": 5,
        **over,
    }


def test_percentile_interpolates() -> None:
    assert percentile([], 50) is None
    assert percentile([4.0], 95) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0


def test_stage_seconds_from_observed_transitions() -> None:
    run = CallRun(
        ref="call_001",
        kind="ses",
        final_state="tamam",
        total_s=40.0,
        seen_s={"beklemede": 0.0, "yaziya_cevriliyor": 5.0, "isleniyor": 25.0},
    )
    assert stage_seconds(run) == {"kuyruk": 5.0, "stt": 20.0, "analiz": 15.0}
    text = CallRun(
        ref="c", kind="metin", final_state="tamam", total_s=12.0, seen_s={"isleniyor": 2.0}
    )
    assert stage_seconds(text) == {"kuyruk": 2.0, "stt": None, "analiz": 10.0}


def test_summarize_batch_counts_outcomes_and_retries() -> None:
    ok = CallRun(
        ref="a",
        kind="metin",
        final_state="tamam",
        total_s=10.0,
        runs=[agent_run("summarizer", 4000), agent_run("crm_extraction", 9000, attempts=2)],
    )
    partial = CallRun(
        ref="b",
        kind="metin",
        final_state="kismi",
        total_s=30.0,
        runs=[agent_run("summarizer", 3000, error_kind="timeout", fallback_from="m")],
    )
    stuck = CallRun(ref="c", kind="metin", final_state="zaman_asimi", total_s=900.0)
    summary = summarize_batch([ok, partial, stuck])
    assert summary["toplam"] == 3
    assert summary["durumlar"] == {"tamam": 1, "kismi": 1, "zaman_asimi": 1}
    assert summary["tamam_orani"] == pytest.approx(33.3)
    assert summary["kismi_dahil_orani"] == pytest.approx(66.7)
    assert summary["yeniden_denenen_agent"] == 1
    assert summary["yedek_modele_gecen_agent"] == 1
    assert summary["zaman_asimi_agent"] == 1
    assert summary["hata_turleri"] == {"timeout": 1}
    assert summary["token"] == 45
    # Zaman aşımına uğrayan çağrı süre dağılımına girmez (bitmemiş).
    assert summary["toplam_sure_s"]["maks"] == 30.0


def test_every_scenario_has_unique_key() -> None:
    keys = [s.key for s in scenarios()]
    assert len(keys) == len(set(keys))
    assert {"hang", "429", "json", "ag-yok", "anahtar-gecersiz", "uzun"} <= set(keys)


def test_synthetic_calls_exist() -> None:
    assert len(synthetic_ids()) >= 30


@pytest.mark.parametrize(
    ("mode", "status", "retry_after"),
    [("429:7", 429, "7"), ("500", 500, None), ("404", 404, None), ("ok", 200, None)],
)
def test_fake_llm_modes(mode: str, status: int, retry_after: str | None) -> None:
    fake = FakeLLM()
    try:
        resp = httpx.post(fake.base_url(mode) + "/chat/completions", json={"messages": []})
    finally:
        fake.close()
    assert resp.status_code == status
    assert resp.headers.get("retry-after") == retry_after


def test_fake_llm_rate_limit_then_ok() -> None:
    fake = FakeLLM()
    try:
        url = fake.base_url("429:1:2") + "/chat/completions"
        codes = [httpx.post(url, json={}).status_code for _ in range(4)]
    finally:
        fake.close()
    assert codes == [429, 429, 200, 200]


def test_fake_llm_garbage_modes_return_200() -> None:
    fake = FakeLLM()
    try:
        for mode in ("prose", "truncated", "wrongshape", "empty"):
            resp = httpx.post(fake.base_url(mode) + "/chat/completions", json={})
            assert resp.status_code == 200
            assert resp.json()["choices"][0]["message"]["role"] == "assistant"
    finally:
        fake.close()

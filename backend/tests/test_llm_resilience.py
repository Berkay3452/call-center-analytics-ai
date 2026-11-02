"""LLM dayanıklılığı (#112): geçici hata sınıflandırması, yedek model, ajan süre bütçesi."""

import asyncio
import json
from typing import Any

import pytest
from pydantic import BaseModel

from app.agents.base import AnalysisContext
from app.agents.orchestrator import Orchestrator
from app.agents.registry import build_default_orchestrator
from app.agents.summarizer import SummarizerAgent
from app.assistant.llm import AssistantLLM, AssistantLLMError
from app.llm.client import is_rate_limit_error, is_transient_llm_error, rate_limit_delay
from tests.conftest import make_settings
from tests.llm_fakes import scripted
from tests.test_agents import SUMMARY_JSON, tuzla_ctx


class APITimeoutError(Exception):
    """OpenAI istemcisinin zaman aşımı istisnasının adını taşıyan sahte sınıf."""


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


# --- Ayarlar ------------------------------------------------------------------------------------


def test_defaults_are_short_and_bounded() -> None:
    s = make_settings()

    assert s.llm_timeout_s == 30
    assert s.llm_max_retries == 1
    assert s.llm_agent_timeout_s == 90
    assert s.llm_fallback_model is None


def test_empty_fallback_model_is_none() -> None:
    assert make_settings(llm_fallback_model="").llm_fallback_model is None
    assert make_settings(llm_fallback_model="   ").llm_fallback_model is None
    assert make_settings(llm_fallback_model="b/yedek").llm_fallback_model == "b/yedek"


def test_fallback_defaults_to_other_tier() -> None:
    s = make_settings(llm_fast_model="m/hizli", llm_smart_model="m/guclu")

    assert s.llm_fallback_for("call_classifier", "fast", "m/hizli") == "m/guclu"
    assert s.llm_fallback_for("call_classifier", "smart", "m/guclu") == "m/hizli"


def test_explicit_fallback_wins_over_other_tier() -> None:
    s = make_settings(llm_fast_model="m/hizli", llm_smart_model="m/guclu", llm_fallback_model="m/y")

    assert s.llm_fallback_for("call_classifier", "fast", "m/hizli") == "m/y"


def test_no_fallback_when_it_equals_primary() -> None:
    s = make_settings(llm_fast_model="m/ayni", llm_smart_model="m/ayni")

    assert s.llm_fallback_for("call_classifier", "fast", "m/ayni") is None


# --- Geçici hata sınıflandırması ----------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError(),
        APITimeoutError("zaman aşımı"),
        StatusError(404),
        StatusError(429),
        StatusError(503),
    ],
)
def test_transient_errors(exc: Exception) -> None:
    assert is_transient_llm_error(exc) is True


@pytest.mark.parametrize(
    "exc", [StatusError(400), StatusError(401), StatusError(403), ValueError("şema"), KeyError("x")]
)
def test_non_transient_errors(exc: Exception) -> None:
    assert is_transient_llm_error(exc) is False


# --- Ajan: yedek model --------------------------------------------------------------------------


async def test_agent_falls_back_on_transient_error() -> None:
    primary = scripted(APITimeoutError("yavaş"))
    backup = scripted(SUMMARY_JSON)
    backup.model_name = "yedek-model"

    result = await SummarizerAgent(model=primary, fallback_model=backup).run(tuzla_ctx())

    assert result.status == "ok"
    assert result.fallback_from == "sahte-model"
    assert result.model == "yedek-model"
    assert len(primary.calls) == 1 and len(backup.calls) == 1


async def test_agent_does_not_fall_back_on_permanent_error() -> None:
    primary = scripted(StatusError(401))
    backup = scripted(SUMMARY_JSON)

    result = await SummarizerAgent(model=primary, fallback_model=backup).run(tuzla_ctx())

    assert result.status == "failed"
    assert result.error_kind == "runtime"
    assert result.fallback_from is None
    assert backup.calls == []


async def test_agent_reports_when_backup_also_fails() -> None:
    primary = scripted(TimeoutError())
    backup = scripted(StatusError(503))

    result = await SummarizerAgent(model=primary, fallback_model=backup).run(tuzla_ctx())

    assert result.status == "failed"
    assert "yedek model de" in (result.error or "")
    assert result.fallback_from == "sahte-model"


async def test_fake_primary_never_opens_real_backup() -> None:
    """Sahte birincil model verilince gerçek sağlayıcıya yedek açılmaz (ağ yok, hata net)."""
    result = await SummarizerAgent(model=scripted(TimeoutError())).run(tuzla_ctx())

    assert result.status == "failed"
    assert result.fallback_from is None


async def test_agent_fallback_still_validates_output() -> None:
    primary = scripted(TimeoutError())
    backup = scripted('{"summary": "Bir. İki. Üç. Dört.", "key_points": []}')

    result = await SummarizerAgent(model=primary, fallback_model=backup).run(tuzla_ctx())

    assert result.status == "failed"
    assert result.error_kind == "validation"


# --- Orkestratör süre bütçesi -------------------------------------------------------------------


def test_orchestrator_budget_comes_from_settings() -> None:
    orch = build_default_orchestrator(settings=make_settings(llm_agent_timeout_s=42.0))

    assert isinstance(orch, Orchestrator)
    assert orch.agent_timeout_s == 42.0


async def test_slow_agent_ends_with_timeout() -> None:
    class SlowModel(type(scripted())):  # type: ignore[misc]
        async def _agenerate(self, *args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(5)

    model = SlowModel(responses=[SUMMARY_JSON], calls=[])
    ctx: AnalysisContext = tuzla_ctx()
    orch = Orchestrator([[SummarizerAgent(model=model)]], agent_timeout_s=0.1)

    result = await orch.run(ctx)

    run = result.runs[0]
    assert run.status == "failed"
    assert run.error_kind == "timeout"


# --- Miço AI: yedek model -----------------------------------------------------------------------


class Reply(BaseModel):
    answer: str


REPLY_JSON = json.dumps({"answer": "tamam"})


async def test_assistant_falls_back_on_transient_error() -> None:
    llm = AssistantLLM(model=scripted(TimeoutError()), fallback_model=scripted(REPLY_JSON))

    reply = await llm.ask("fast", "sistem", "soru", Reply)

    assert reply.answer == "tamam"


async def test_assistant_no_fallback_on_permanent_error() -> None:
    backup = scripted(REPLY_JSON)
    llm = AssistantLLM(model=scripted(StatusError(401)), fallback_model=backup)

    with pytest.raises(AssistantLLMError):
        await llm.ask("fast", "sistem", "soru", Reply)

    assert backup.calls == []


async def test_assistant_reports_double_failure() -> None:
    llm = AssistantLLM(model=scripted(TimeoutError()), fallback_model=scripted(StatusError(503)))

    with pytest.raises(AssistantLLMError, match="yedek model de"):
        await llm.ask("fast", "sistem", "soru", Reply)


async def test_assistant_keeps_backup_for_fix_round() -> None:
    """Düzeltme turu da yedek modelle sürer; birincil tekrar denenmez."""
    primary = scripted(TimeoutError())
    backup = scripted("bozuk", REPLY_JSON)
    llm = AssistantLLM(model=primary, fallback_model=backup)

    reply = await llm.ask("fast", "sistem", "soru", Reply)

    assert reply.answer == "tamam"
    assert len(primary.calls) == 1 and len(backup.calls) == 2


# --- 429: bekle ve yeniden dene (#216) ----------------------------------------------------------


class RateLimitError(Exception):
    """OpenAI istemcisinin 429 istisnasının adını taşıyan sahte sınıf (başlıklı)."""

    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("429 Too Many Requests")
        self.status_code = 429
        self.response = type(
            "R", (), {"headers": {"retry-after": retry_after} if retry_after else {}}
        )()


def test_rate_limit_detection() -> None:
    assert is_rate_limit_error(StatusError(429)) is True
    assert is_rate_limit_error(RateLimitError()) is True
    assert is_rate_limit_error(StatusError(500)) is False
    assert is_rate_limit_error(TimeoutError()) is False


def test_rate_limit_delay_prefers_retry_after_and_is_capped() -> None:
    assert rate_limit_delay(RateLimitError("7"), 0, 4.0) == 7.0
    assert rate_limit_delay(RateLimitError("600"), 0, 4.0) == 30.0
    # Başlık yoksa üstel: 4, 8, 16 sn (+ en çok %25 rastgele pay).
    for attempt, base in [(0, 4.0), (1, 8.0), (2, 16.0)]:
        assert base <= rate_limit_delay(StatusError(429), attempt, 4.0) <= base * 1.25
    assert rate_limit_delay(StatusError(429), 10, 4.0) <= 30.0 * 1.25


async def test_agent_waits_and_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.agents.llm_agent.asyncio.sleep", fake_sleep)
    model = scripted(RateLimitError("2"), RateLimitError("3"), SUMMARY_JSON)

    result = await SummarizerAgent(model=model, settings=make_settings()).run(tuzla_ctx())

    assert result.status == "ok"
    assert sleeps == [2.0, 3.0]
    assert len(model.calls) == 3


async def test_agent_gives_up_after_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr("app.agents.llm_agent.asyncio.sleep", fake_sleep)
    model = scripted(*[RateLimitError("1") for _ in range(10)])

    result = await SummarizerAgent(
        model=model, settings=make_settings(llm_rate_limit_retries=2)
    ).run(tuzla_ctx())

    assert (result.status, result.error_kind) == ("failed", "runtime")
    assert len(model.calls) == 3  # ilk deneme + 2 yeniden deneme


async def test_rate_limit_retries_zero_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(delay: float) -> None:
        raise AssertionError("beklememeliydi")

    monkeypatch.setattr("app.agents.llm_agent.asyncio.sleep", boom)
    model = scripted(RateLimitError())

    result = await SummarizerAgent(
        model=model, settings=make_settings(llm_rate_limit_retries=0)
    ).run(tuzla_ctx())

    assert result.status == "failed"
    assert len(model.calls) == 1

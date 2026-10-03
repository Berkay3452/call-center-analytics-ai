"""Yapay zekâ katmanı ve işçi altyapısının ön hazırlık testleri (ağ çağrısı yapılmaz)."""

from collections.abc import Callable
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.agents.base import AgentResult, AnalysisContext, BaseAgent, Segment
from app.core.config import Settings
from app.llm.client import LLMNotConfiguredError, get_chat_model
from app.workers.tasks.system import ping


def test_celery_ping_task_runs_locally() -> None:
    # apply(): broker'a gitmeden görevi aynı süreçte çalıştırır.
    assert ping.apply().get() == "pong"


def test_llm_requires_model_name(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(LLMNotConfiguredError):
        get_chat_model("fast", settings_factory(llm_fast_model=None))


def test_llm_model_is_built_for_groq(settings_factory: Callable[..., Settings]) -> None:
    s = settings_factory(llm_api_key="test-key", llm_fast_model="ornek-model")
    model = get_chat_model("fast", s)
    assert model.model_name == "ornek-model"  # type: ignore[attr-defined]
    assert "groq.com" in str(model.openai_api_base)  # type: ignore[attr-defined]


class _EchoOutput(BaseModel):
    segment_count: int


class _EchoAgent(BaseAgent[_EchoOutput]):
    """Sözleşmeyi doğrulamak için LLM çağırmayan sahte ajan."""

    name: ClassVar[str] = "echo"
    prompt_version: ClassVar[str] = "echo.v1"
    output_schema: ClassVar[type[BaseModel]] = _EchoOutput

    async def run(self, ctx: AnalysisContext) -> AgentResult[_EchoOutput]:
        return AgentResult[_EchoOutput](
            agent=self.name,
            status="ok",
            output=_EchoOutput(segment_count=len(ctx.segments)),
            prompt_version=self.prompt_version,
        )


async def test_agent_contract() -> None:
    ctx = AnalysisContext(
        call_id=uuid4(),
        segments=[
            Segment(idx=0, speaker="rep", start_ms=0, end_ms=1000, text_masked="Merhaba"),
            Segment(idx=1, speaker="customer", start_ms=1000, end_ms=2000, text_masked="Selam"),
        ],
    )
    result = await _EchoAgent().run(ctx)
    assert result.status == "ok"
    assert result.output is not None
    assert result.output.segment_count == 2

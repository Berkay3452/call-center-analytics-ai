"""Orkestratör testleri: LLM çağırmayan sahte agent'larla akış kuralları doğrulanır."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar
from uuid import uuid4

import pytest
from pydantic import BaseModel, Field

from app.agents.base import (
    AgentErrorKind,
    AgentResult,
    AnalysisContext,
    BaseAgent,
    CallInfo,
    Segment,
)
from app.agents.orchestrator import OrchestrationResult, Orchestrator, run_analysis
from app.agents.registry import REQUEST_EXTRACTION, SALES_OUTCOME, SUMMARY, TRIAGE


class _Out(BaseModel):
    label: str = Field(min_length=1)


Behaviour = Callable[[AnalysisContext, int], Awaitable[AgentResult[_Out]]]


class _FakeAgent(BaseAgent[_Out]):
    """Davranışı dışarıdan verilen sahte agent; aldığı bağlamları kaydeder."""

    name: ClassVar[str] = "fake"
    prompt_version: ClassVar[str] = "fake.v1"
    output_schema: ClassVar[type[BaseModel]] = _Out

    def __init__(self, behaviour: Behaviour) -> None:
        self.behaviour = behaviour
        self.seen: list[AnalysisContext] = []

    async def run(self, ctx: AnalysisContext) -> AgentResult[_Out]:
        self.seen.append(ctx)
        return await self.behaviour(ctx, len(self.seen))


def fake(name: str, behaviour: Behaviour | None = None) -> _FakeAgent:
    async def ok(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        return AgentResult[_Out](agent=name, status="ok", output=_Out(label=name))

    cls = type(f"Fake_{name}", (_FakeAgent,), {"name": name})
    agent: _FakeAgent = cls(behaviour or ok)
    return agent


def fail(name: str, kind: AgentErrorKind = "runtime") -> Behaviour:
    async def behaviour(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        return AgentResult[_Out](agent=name, status="failed", error="bozuldu", error_kind=kind)

    return behaviour


def make_ctx() -> AnalysisContext:
    return AnalysisContext(
        call_id=uuid4(),
        segments=[
            Segment(
                idx=0,
                speaker="customer",
                start_ms=0,
                end_ms=4000,
                text_masked="Motor çalışıyor ama gaz verdiğimde devir yükselmiyor.",
            ),
            Segment(idx=1, speaker="rep", start_ms=4000, end_ms=6000, text_masked="Hangi marina?"),
        ],
        call_info=CallInfo(answer_delay_s=12),
    )


class _ListRecorder:
    def __init__(self) -> None:
        self.records: list[OrchestrationResult] = []

    async def record(self, result: OrchestrationResult) -> None:
        self.records.append(result)


# --- Tam başarı ve bağlam aktarımı -------------------------------------------------------------


async def test_all_agents_ok_gives_tamam_and_passes_prior() -> None:
    triage = fake(TRIAGE)
    second = [fake(REQUEST_EXTRACTION), fake(SALES_OUTCOME), fake(SUMMARY)]
    recorder = _ListRecorder()
    orch = Orchestrator([[triage], second], recorder=recorder)

    result = await orch.run(make_ctx())

    assert result.status == "tamam"
    assert result.errors == {}
    assert result.outputs[SUMMARY] == {"label": SUMMARY}
    assert [r.agent for r in result.runs] == [TRIAGE, REQUEST_EXTRACTION, SALES_OUTCOME, SUMMARY]
    assert all(r.attempts == 1 for r in result.runs)
    # İkinci aşama Triage'ın çıktısını görür; aynı aşamadakilerin çıktısını görmez.
    for agent in second:
        assert agent.seen[0].prior == {TRIAGE: {"label": TRIAGE}}
    assert triage.seen[0].prior == {}
    # Çağrı bilgisi agent'lara ulaşır; kayıtçı bir kez çağrılır.
    assert triage.seen[0].call_info is not None
    assert recorder.records == [result]


async def test_same_stage_agents_run_in_parallel() -> None:
    barrier = asyncio.Barrier(3)

    def waits_for_others(name: str) -> Behaviour:
        async def behaviour(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
            # Üçü aynı anda çalışmıyorsa bariyer hiç açılmaz ve zaman aşımı olur.
            await asyncio.wait_for(barrier.wait(), timeout=2)
            return AgentResult[_Out](agent=name, status="ok", output=_Out(label=name))

        return behaviour

    stage = [fake(n, waits_for_others(n)) for n in ("a", "b", "c")]
    result = await Orchestrator([stage]).run(make_ctx())

    assert result.status == "tamam"


# --- Kısmi başarı ------------------------------------------------------------------------------


async def test_failed_agent_gives_kismi_and_keeps_others() -> None:
    orch = Orchestrator(
        [[fake(TRIAGE)], [fake(REQUEST_EXTRACTION), fake(SALES_OUTCOME, fail(SALES_OUTCOME))]]
    )

    result = await orch.run(make_ctx())

    assert result.status == "kismi"
    assert set(result.outputs) == {TRIAGE, REQUEST_EXTRACTION}
    assert result.errors == {SALES_OUTCOME: "bozuldu"}
    failed = next(r for r in result.runs if r.agent == SALES_OUTCOME)
    assert (failed.status, failed.error_kind, failed.attempts) == ("failed", "runtime", 1)


async def test_failed_first_stage_does_not_stop_next_stage() -> None:
    summary = fake(SUMMARY)
    orch = Orchestrator([[fake(TRIAGE, fail(TRIAGE))], [summary]])

    result = await orch.run(make_ctx())

    assert result.status == "kismi"
    assert summary.seen[0].prior == {}  # başarısız agent'ın çıktısı aktarılmaz


async def test_all_failed_gives_basarisiz() -> None:
    orch = Orchestrator([[fake("a", fail("a")), fake("b", fail("b", "timeout"))]])

    result = await orch.run(make_ctx())

    assert result.status == "basarisiz"
    assert result.outputs == {}
    assert set(result.errors) == {"a", "b"}


async def test_exception_is_contained_as_runtime_error() -> None:
    async def crash(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        raise RuntimeError("beklenmeyen")

    result = await Orchestrator([[fake("ok"), fake("crash", crash)]]).run(make_ctx())

    assert result.status == "kismi"
    run = next(r for r in result.runs if r.agent == "crash")
    assert run.error_kind == "runtime"
    assert "beklenmeyen" in (run.error or "")


async def test_timeout_is_not_retried() -> None:
    async def slow(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        await asyncio.sleep(5)
        raise AssertionError("buraya gelinmemeli")

    agent = fake("slow", slow)
    result = await Orchestrator([[agent]], agent_timeout_s=0.05).run(make_ctx())

    assert result.runs[0].error_kind == "timeout"
    assert len(agent.seen) == 1


# --- Doğrulama ve düzeltme ---------------------------------------------------------------------


async def test_validation_error_gets_one_fix_with_feedback() -> None:
    async def wrong_then_right(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        if attempt == 1:
            return AgentResult[_Out](
                agent="fixer", status="failed", error="label eksik", error_kind="validation"
            )
        return AgentResult[_Out](agent="fixer", status="ok", output=_Out(label="düzeldi"))

    agent = fake("fixer", wrong_then_right)
    result = await Orchestrator([[agent]]).run(make_ctx())

    assert result.status == "tamam"
    assert result.runs[0].attempts == 2
    assert agent.seen[0].feedback is None
    assert agent.seen[1].feedback == "label eksik"


async def test_validation_error_twice_fails_after_two_attempts() -> None:
    agent = fake("stubborn", fail("stubborn", "validation"))
    result = await Orchestrator([[agent]]).run(make_ctx())

    assert result.status == "basarisiz"
    assert result.runs[0].attempts == 2
    assert result.runs[0].error_kind == "validation"


async def test_orchestrator_revalidates_output_against_schema() -> None:
    async def sneaky(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        # model_construct doğrulamayı atlar; boş etiket şemaya aykırı.
        return AgentResult[_Out](agent="sneaky", status="ok", output=_Out.model_construct(label=""))

    agent = fake("sneaky", sneaky)
    result = await Orchestrator([[agent]]).run(make_ctx())

    assert result.status == "basarisiz"
    assert result.runs[0].error_kind == "validation"
    assert len(agent.seen) == 2  # düzeltme şansı verildi
    assert "label" in (agent.seen[1].feedback or "")


async def test_ok_without_output_is_validation_error() -> None:
    async def empty(ctx: AnalysisContext, attempt: int) -> AgentResult[_Out]:
        return AgentResult[_Out](agent="empty", status="ok")

    result = await Orchestrator([[fake("empty", empty)]], max_fix_attempts=0).run(make_ctx())

    assert result.runs[0].error_kind == "validation"
    assert result.runs[0].attempts == 1


# --- Kurulum ve varsayılan akış ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        ([], "En az bir"),
        ([[fake("a")], []], "boş"),
        ([[fake("a")], [fake("a")]], "benzersiz"),
        ([[fake("results")]], "ayrılmış"),
    ],
)
def test_invalid_stages_are_rejected(stages: list[Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Orchestrator(stages)


async def test_default_flow_runs_end_to_end_with_pending_agents() -> None:
    ctx = make_ctx()
    result = await run_analysis(ctx.call_id, ctx.segments, ctx.call_info)

    assert result.call_id == ctx.call_id
    assert [r.agent for r in result.runs] == [TRIAGE, REQUEST_EXTRACTION, SALES_OUTCOME, SUMMARY]
    assert {r.status for r in result.runs} == {"skipped"}
    # Hiçbir agent henüz yazılmadığı için analiz başarılı sayılmaz.
    assert result.status == "basarisiz"

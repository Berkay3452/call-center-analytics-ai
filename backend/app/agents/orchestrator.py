"""Çağrı analizi orkestratörü (LangGraph).

Agent'lar aşamalar (stage) halinde çalışır. Aynı aşamadaki agent'lar birbirinden bağımsızdır ve
paralel çalışır; bir sonraki aşama, öncekilerin başarılı çıktılarını `ctx.prior` içinde görür.
Varsayılan akış (Sistem mimarisi v3 §6.1):

    Çağrı Sınıflandırma → (CRM Bilgi Çıkarım ‖ Satış Analiz ‖ Özetleme) → sonuç

Kurallar:
- Her agent çıktısı kendi Pydantic şemasıyla yeniden doğrulanır.
- Doğrulama hatasında agent'a hata mesajıyla (`ctx.feedback`) en fazla `max_fix_attempts` kez
  düzeltme şansı verilir. Çalışma zamanı hatası ve zaman aşımı tekrar denenmez.
- Bir agent çökerse diğerlerinin sonucu atılmaz; analiz "kismi" tamamlanır.
- Agent istisna fırlatsa bile orkestratör durmaz (sözleşme ihlali "runtime" hatası sayılır).

LangGraph `ai` ekstrasındadır ve tembel import edilir; API bu paket olmadan da açılır.
"""

import asyncio
import operator
import time
from collections.abc import Awaitable, Sequence
from typing import Annotated, Any, Protocol, TypedDict
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, ValidationError

from app.agents.base import AgentResult, AnalysisContext, BaseAgent, CallInfo, Segment
from app.schemas.analysis import AgentRun, AnalysisResult, AnalysisStatus

log = structlog.get_logger(__name__)

Stage = Sequence[BaseAgent[Any]]


class OrchestrationResult(BaseModel):
    """Orkestratörün birleşik çıktısı. Agent çıktıları adlarıyla `outputs` içindedir."""

    call_id: UUID
    status: AnalysisStatus
    outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
    runs: list[AgentRun] = Field(default_factory=list)
    latency_ms: int = 0

    def to_analysis_result(self) -> AnalysisResult:
        """Agent adına göre toplanan çıktıları şemalı birleşik sonuca çevirir."""
        return AnalysisResult.from_outputs(
            call_id=self.call_id,
            status=self.status,
            outputs=self.outputs,
            errors=self.errors,
            runs=self.runs,
        )


class RunRecorder(Protocol):
    """Agent çalışma kayıtlarını saklayan bileşen.

    Veritabanı tabloları (#5, #6) hazır olunca `agent_runs` tablosuna yazan uygulama eklenecek.
    """

    async def record(self, result: OrchestrationResult) -> None: ...


class NullRecorder:
    """Hiçbir yere yazmayan kayıtçı; yalnızca log düşer."""

    async def record(self, result: OrchestrationResult) -> None:
        log.info(
            "analysis.finished",
            call_id=str(result.call_id),
            status=result.status,
            agents={r.agent: r.status for r in result.runs},
            latency_ms=result.latency_ms,
        )


class _GraphState(TypedDict):
    ctx: AnalysisContext
    # Paralel agent'lar aynı süper adımda yazar; sözlükler birleştirilir.
    results: Annotated[dict[str, AgentResult[Any]], operator.or_]


_RESERVED_NAMES = frozenset(_GraphState.__annotations__)


class _NodeFn(Protocol):
    """LangGraph düğüm imzası (parametre adı `state` olmalı)."""

    def __call__(self, state: _GraphState) -> Awaitable[dict[str, Any]]: ...


def _decide_status(results: dict[str, AgentResult[Any]]) -> AnalysisStatus:
    """Hepsi başarılıysa "tamam"; en az biri başarılıysa "kismi"; hiçbiri değilse "basarisiz".

    Atlanan ("skipped") agent'lar başarı sayılmaz; tamamı atlanırsa sonuç "basarisiz" olur.
    """
    ok = sum(1 for r in results.values() if r.status == "ok")
    if ok == 0:
        return "basarisiz"
    return "tamam" if ok == len(results) else "kismi"


class Orchestrator:
    """Agent aşamalarını LangGraph grafiği olarak kurar ve çalıştırır."""

    def __init__(
        self,
        stages: Sequence[Stage],
        *,
        max_fix_attempts: int = 1,
        agent_timeout_s: float | None = 120.0,
        recorder: RunRecorder | None = None,
    ) -> None:
        names = [agent.name for stage in stages for agent in stage]
        if not names or any(not stage for stage in stages):
            raise ValueError("En az bir aşama olmalı ve hiçbir aşama boş olmamalı.")
        if len(names) != len(set(names)):
            raise ValueError(f"Agent adları benzersiz olmalı: {names}")
        if clash := _RESERVED_NAMES.intersection(names):
            raise ValueError(f"Agent adı ayrılmış bir ad olamaz: {sorted(clash)}")

        self.stages = [list(stage) for stage in stages]
        self.max_fix_attempts = max_fix_attempts
        self.agent_timeout_s = agent_timeout_s
        self.recorder: RunRecorder = recorder or NullRecorder()
        self._graph = self._build_graph()

    @property
    def agent_names(self) -> list[str]:
        return [agent.name for stage in self.stages for agent in stage]

    # --- Grafik ---------------------------------------------------------------------------

    def _build_graph(self) -> Any:
        from langgraph.graph import END, START, StateGraph  # tembel import (ai ekstrası)

        builder = StateGraph(_GraphState)
        for stage in self.stages:
            for agent in stage:
                builder.add_node(agent.name, self._make_node(agent))

        for agent in self.stages[0]:
            builder.add_edge(START, agent.name)
        # Bir sonraki aşamanın her agent'ı, önceki aşamanın TAMAMI bitince başlar.
        for prev, nxt in zip(self.stages, self.stages[1:], strict=False):
            prev_names = [a.name for a in prev]
            for agent in nxt:
                builder.add_edge(prev_names, agent.name)
        builder.add_edge([a.name for a in self.stages[-1]], END)
        return builder.compile()

    def _make_node(self, agent: BaseAgent[Any]) -> "_NodeFn":
        async def node(state: _GraphState) -> dict[str, Any]:
            prior = {
                name: result.output.model_dump(mode="json")
                for name, result in state["results"].items()
                if result.status == "ok" and result.output is not None
            }
            ctx = state["ctx"].model_copy(update={"prior": prior, "feedback": None})
            result = await self._run_agent(agent, ctx)
            return {"results": {agent.name: result}}

        return node

    # --- Tek agent çalıştırma ---------------------------------------------------------------

    async def _run_agent(self, agent: BaseAgent[Any], ctx: AnalysisContext) -> AgentResult[Any]:
        started = time.perf_counter()
        attempts = 0
        tokens_in = tokens_out = 0
        while True:
            attempts += 1
            result = await self._call_once(agent, ctx)
            tokens_in += result.tokens_in
            tokens_out += result.tokens_out
            if result.status == "ok":
                result = self._validate(agent, result)

            can_fix = attempts <= self.max_fix_attempts
            if result.status == "failed" and result.error_kind == "validation" and can_fix:
                log.warning("agent.fix_requested", agent=agent.name, error=result.error)
                ctx = ctx.model_copy(update={"feedback": result.error})
                continue
            break

        result = result.model_copy(
            update={
                "attempts": attempts,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        )
        if result.status == "failed":
            log.warning(
                "agent.failed", agent=agent.name, kind=result.error_kind, error=result.error
            )
        return result

    async def _call_once(self, agent: BaseAgent[Any], ctx: AnalysisContext) -> AgentResult[Any]:
        try:
            return await asyncio.wait_for(agent.run(ctx), timeout=self.agent_timeout_s)
        except TimeoutError:
            return AgentResult(
                agent=agent.name,
                status="failed",
                error=f"Süre sınırı aşıldı ({self.agent_timeout_s} sn).",
                error_kind="timeout",
            )
        except Exception as exc:  # sözleşme ihlali: agent istisna fırlatmamalıydı
            log.exception("agent.crashed", agent=agent.name)
            return AgentResult(
                agent=agent.name,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                error_kind="runtime",
            )

    @staticmethod
    def _validate(agent: BaseAgent[Any], result: AgentResult[Any]) -> AgentResult[Any]:
        """Başarılı görünen çıktıyı agent'ın şemasıyla yeniden doğrular."""
        if result.output is None:
            return result.model_copy(
                update={
                    "status": "failed",
                    "error": "Agent başarılı döndü ama çıktı boş.",
                    "error_kind": "validation",
                }
            )
        try:
            # model_dump → model_validate: `model_construct` ile atlatılmış doğrulamayı da yakalar.
            data = (
                result.output.model_dump()
                if isinstance(result.output, BaseModel)
                else result.output
            )
            output = agent.output_schema.model_validate(data)
        except ValidationError as exc:
            return result.model_copy(
                update={
                    "status": "failed",
                    "output": None,
                    "error": str(exc),
                    "error_kind": "validation",
                }
            )
        return result.model_copy(update={"output": output})

    # --- Dış arayüz ---------------------------------------------------------------------------

    async def run(self, ctx: AnalysisContext) -> OrchestrationResult:
        started = time.perf_counter()
        final = await self._graph.ainvoke({"ctx": ctx, "results": {}})
        results: dict[str, AgentResult[Any]] = final["results"]

        ordered = [results[name] for name in self.agent_names]
        outcome = OrchestrationResult(
            call_id=ctx.call_id,
            status=_decide_status(results),
            outputs={
                r.agent: r.output.model_dump(mode="json")
                for r in ordered
                if r.status == "ok" and r.output is not None
            },
            errors={r.agent: r.error or "bilinmeyen hata" for r in ordered if r.status == "failed"},
            runs=[AgentRun.from_result(r) for r in ordered],
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        await self.recorder.record(outcome)
        return outcome


async def run_analysis(
    call_id: UUID,
    segments: list[Segment],
    call_info: CallInfo | None = None,
    *,
    orchestrator: Orchestrator | None = None,
) -> OrchestrationResult:
    """Bir çağrının maskelenmiş transkriptini analiz eder.

    `orchestrator` verilmezse varsayılan akış (bkz. `app.agents.registry`) kullanılır.
    """
    if orchestrator is None:
        from app.agents.registry import build_default_orchestrator

        orchestrator = build_default_orchestrator()
    ctx = AnalysisContext(call_id=call_id, segments=segments, call_info=call_info)
    return await orchestrator.run(ctx)

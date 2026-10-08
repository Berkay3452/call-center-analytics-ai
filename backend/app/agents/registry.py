"""Varsayılan çağrı analizi akışı: hangi agent hangi aşamada çalışır.

Gerçek agent'lar yazıldıkça (#17 Triage, #18 Talep Çıkarım, #19 Satış Sonucu, #20 Özet)
ilgili yer tutucu kendi sınıfıyla değiştirilir; akışın kendisi değişmez.
"""

from typing import Any, ClassVar

from pydantic import BaseModel

from app.agents.base import AgentResult, AnalysisContext, BaseAgent
from app.agents.orchestrator import Orchestrator, RunRecorder, Stage

# Agent adları; orkestratör çıktısında (`outputs`, `runs`) ve veritabanında bu adlar görünür.
TRIAGE = "triage"
REQUEST_EXTRACTION = "request_extraction"
SALES_OUTCOME = "sales_outcome"
SUMMARY = "summary"


class _Empty(BaseModel):
    pass


class PendingAgent(BaseAgent[_Empty]):
    """Henüz yazılmamış agent'ın yerini tutar; çalıştırılınca "skipped" döner."""

    name: ClassVar[str] = "pending"
    prompt_version: ClassVar[str] = "-"
    output_schema: ClassVar[type[BaseModel]] = _Empty

    async def run(self, ctx: AnalysisContext) -> AgentResult[_Empty]:
        return AgentResult(agent=self.name, status="skipped", error="Agent henüz yazılmadı.")


def _pending(agent_name: str) -> BaseAgent[Any]:
    cls = type(f"Pending_{agent_name}", (PendingAgent,), {"name": agent_name})
    agent: BaseAgent[Any] = cls()
    return agent


def default_stages() -> list[Stage]:
    """Sistem mimarisi v3 §6.1: Triage → (Talep Çıkarım ‖ Satış Sonucu ‖ Özet)."""
    return [
        [_pending(TRIAGE)],
        [_pending(REQUEST_EXTRACTION), _pending(SALES_OUTCOME), _pending(SUMMARY)],
    ]


def build_default_orchestrator(recorder: RunRecorder | None = None) -> Orchestrator:
    return Orchestrator(default_stages(), recorder=recorder)

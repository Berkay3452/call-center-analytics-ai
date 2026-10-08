"""Varsayılan çağrı analizi akışı: hangi agent hangi aşamada çalışır.

Gerçek agent'lar yazıldıkça (#17 Çağrı Sınıflandırma, #18 CRM Bilgi Çıkarım, #19 Satış Analiz,
#20 Özetleme) ilgili yer tutucu kendi sınıfıyla değiştirilir; akışın kendisi değişmez.
"""

from typing import Any, ClassVar

from pydantic import BaseModel

from app.agents.base import AgentResult, AnalysisContext, BaseAgent
from app.agents.orchestrator import Orchestrator, RunRecorder, Stage

# Agent adları; orkestratör çıktısında (`outputs`, `runs`) ve veritabanında bu adlar görünür.
CALL_CLASSIFIER = "call_classifier"
CRM_EXTRACTION = "crm_extraction"
SALES_ANALYZER = "sales_analyzer"
SUMMARIZER = "summarizer"


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
    """Mimari v3.1 §6.1: Çağrı Sınıflandırma → (CRM Bilgi Çıkarım ‖ Satış Analiz ‖ Özetleme)."""
    return [
        [_pending(CALL_CLASSIFIER)],
        [_pending(CRM_EXTRACTION), _pending(SALES_ANALYZER), _pending(SUMMARIZER)],
    ]


def build_default_orchestrator(recorder: RunRecorder | None = None) -> Orchestrator:
    return Orchestrator(default_stages(), recorder=recorder)

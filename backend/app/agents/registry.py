"""Varsayılan çağrı analizi akışı: hangi agent hangi aşamada çalışır.

Yeni bir agent eklemek için sınıfını yazıp buradaki uygun aşamaya eklemek yeterlidir; orkestratör
değişmez.
"""

from app.agents.call_classifier import CallClassifierAgent
from app.agents.crm_extraction import CrmExtractionAgent
from app.agents.orchestrator import Orchestrator, RunRecorder, Stage
from app.agents.sales_analyzer import SalesAnalyzerAgent
from app.agents.summarizer import SummarizerAgent
from app.core.config import Settings


def default_stages(settings: Settings | None = None) -> list[Stage]:
    """Mimari v3.1 §6.1: Çağrı Sınıflandırma → (CRM Bilgi Çıkarım ‖ Satış Analiz ‖ Özetleme).

    `settings` verilmezse LLM ayarları `.env`'den okunur (testlerde bilerek verilir).
    """
    return [
        [CallClassifierAgent(settings=settings)],
        [
            CrmExtractionAgent(settings=settings),
            SalesAnalyzerAgent(settings=settings),
            SummarizerAgent(settings=settings),
        ],
    ]


def build_default_orchestrator(
    recorder: RunRecorder | None = None, settings: Settings | None = None
) -> Orchestrator:
    return Orchestrator(default_stages(settings), recorder=recorder)

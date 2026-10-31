"""Varsayılan çağrı analizi akışı: hangi agent hangi aşamada çalışır.

Yeni bir agent eklemek için sınıfını yazıp buradaki uygun aşamaya eklemek yeterlidir; orkestratör
değişmez.
"""

from typing import Any

from app.agents.base import BaseAgent
from app.agents.call_classifier import CallClassifierAgent
from app.agents.crm_extraction import CrmExtractionAgent
from app.agents.orchestrator import Orchestrator, RunRecorder, Stage
from app.agents.sales_analyzer import SalesAnalyzerAgent
from app.agents.summarizer import SummarizerAgent
from app.core.config import Settings, get_settings


def default_stages(settings: Settings | None = None) -> list[Stage]:
    """Varsayılan akış: dört agent TEK aşamada, paralel (#162).

    Eskiden Çağrı Sınıflandırma önce çalışıp ardından (CRM Bilgi Çıkarım ‖ Satış Analiz ‖
    Özetleme) geliyordu; ancak ikinci aşamadaki hiçbir agent sınıflandırma çıktısını kullanmıyor
    (yalnızca prompt'a ek bağlam olarak giriyordu). Sıra, sınıflandırmanın süresini (3-9 sn)
    boşuna uçtan uca süreye ekliyordu. `ANALYSIS_CLASSIFIER_FIRST=true` eski sırayı geri getirir.

    `settings` verilmezse LLM ayarları `.env`'den okunur (testlerde bilerek verilir).
    """
    classifier = CallClassifierAgent(settings=settings)
    others: list[BaseAgent[Any]] = [
        CrmExtractionAgent(settings=settings),
        SalesAnalyzerAgent(settings=settings),
        SummarizerAgent(settings=settings),
    ]
    if (settings or get_settings()).analysis_classifier_first:
        return [[classifier], others]
    return [[classifier, *others]]


def build_default_orchestrator(
    recorder: RunRecorder | None = None, settings: Settings | None = None
) -> Orchestrator:
    cfg = settings or get_settings()
    return Orchestrator(
        default_stages(cfg), agent_timeout_s=cfg.llm_agent_timeout_s, recorder=recorder
    )

"""Çağrı Sınıflandırma Agent'ı (#17).

Görüşmenin tipini belirler: yeni müşteri, servis, teklif, acil, bilgi. Çağrı Analitiği'ndeki
"yeni müşteri, servis talebi, teklif talebi, acil servis" KPI'ları bu agent'tan gelir; ikinci
aşamadaki agent'lar da çıktısını bağlam olarak görür.
"""

from typing import ClassVar

from pydantic import BaseModel

from app.agents.base import ModelTier
from app.agents.llm_agent import LLMAgent
from app.agents.names import CALL_CLASSIFIER
from app.schemas.analysis import CallClassification


class CallClassifierAgent(LLMAgent[CallClassification]):
    name: ClassVar[str] = CALL_CLASSIFIER
    prompt_file: ClassVar[str] = "call_classifier"
    prompt_version: ClassVar[str] = "call_classifier.v1"
    output_schema: ClassVar[type[BaseModel]] = CallClassification
    # Sınıflandırma hafif bir iş; hızlı model yeterli.
    model_tier: ClassVar[ModelTier] = "fast"

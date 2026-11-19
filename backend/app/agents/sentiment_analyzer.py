"""Duygu Analiz Agent'ı (#333).

Müşterinin görüşme boyunca genel duygu durumunu (olumlu / nötr / olumsuz) ve açık bir şikâyet
olup olmadığını belirler. Çağrı detayındaki duygu rozetini ve şikâyetli çağrı oranını besler.

`complaint=true` ise `sentiment=olumsuz` olmalıdır; kural şemada doğrulanır, ihlal edilirse
orkestratör hata mesajıyla agent'a bir kez daha sorar. Konuşmada geçmeyen alıntı kaldırılır.
"""

from typing import ClassVar

import structlog
from pydantic import BaseModel

from app.agents.base import AnalysisContext, ModelTier
from app.agents.grounding import is_grounded, transcript_text
from app.agents.llm_agent import LLMAgent
from app.agents.names import SENTIMENT_ANALYZER
from app.schemas.analysis import CustomerSentiment

log = structlog.get_logger(__name__)


class SentimentAnalyzerAgent(LLMAgent[CustomerSentiment]):
    name: ClassVar[str] = SENTIMENT_ANALYZER
    prompt_file: ClassVar[str] = "sentiment_analyzer"
    prompt_version: ClassVar[str] = "sentiment_analyzer.v2"
    output_schema: ClassVar[type[BaseModel]] = CustomerSentiment
    # Ton ve imayı ayırt etmek ince bir yorum gerektirir; güçlü model kullanılır.
    model_tier: ClassVar[ModelTier] = "smart"

    def postprocess(self, output: CustomerSentiment, ctx: AnalysisContext) -> CustomerSentiment:
        """Konuşmada geçmeyen alıntıyı kaldırır; kararın kendisine dokunmaz."""
        if output.evidence and not is_grounded(output.evidence, transcript_text(ctx.segments)):
            log.info("sentiment_analyzer.evidence_dropped", reason="alıntı konuşmada geçmiyor")
            return output.model_copy(update={"evidence": None})
        return output

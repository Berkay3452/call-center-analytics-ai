"""Satış Analiz Agent'ı (#19).

Görüşmenin satışa dönüşüp dönüşmediğini ve dönüşmediyse nedenini belirler. Çağrı Analitiği'ndeki
"satışa dönüşen" ve "kaybedilme nedeni" KPI'ları bu agent'tan gelir.

`loss_reason` yalnızca `kaybedildi` iken dolu olabilir; bu kural şemada doğrulanır ve ihlal
edilirse orkestratör hata mesajıyla agent'a bir kez daha sorar.
"""

from typing import ClassVar

import structlog
from pydantic import BaseModel

from app.agents.base import AnalysisContext, ModelTier
from app.agents.grounding import is_grounded, transcript_text
from app.agents.llm_agent import LLMAgent
from app.agents.names import SALES_ANALYZER
from app.schemas.analysis import SalesAnalysis

log = structlog.get_logger(__name__)


class SalesAnalyzerAgent(LLMAgent[SalesAnalysis]):
    name: ClassVar[str] = SALES_ANALYZER
    prompt_file: ClassVar[str] = "sales_analyzer"
    prompt_version: ClassVar[str] = "sales_analyzer.v1"
    output_schema: ClassVar[type[BaseModel]] = SalesAnalysis
    # Kayıp nedenini ayırt etmek ince bir yorum gerektirir; güçlü model kullanılır.
    model_tier: ClassVar[ModelTier] = "smart"

    def postprocess(self, output: SalesAnalysis, ctx: AnalysisContext) -> SalesAnalysis:
        """Konuşmada geçmeyen alıntıyı kaldırır; kararın kendisine dokunmaz."""
        if output.evidence and not is_grounded(output.evidence, transcript_text(ctx.segments)):
            log.info("sales_analyzer.evidence_dropped", reason="alıntı konuşmada geçmiyor")
            return output.model_copy(update={"evidence": None})
        return output

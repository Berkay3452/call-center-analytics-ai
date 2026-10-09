"""CRM Bilgi Çıkarım Agent'ı (#18).

Görüşmeden CRM kaydı önerisinin 7 alanını çıkarır: müşteri talebi, lokasyon, problem, hizmet
biçimi, aciliyet, potansiyel iş, sonraki aksiyon. Hocanın "çağrıdan CRM kaydı" işinin kalbidir.
"""

from typing import ClassVar

import structlog
from pydantic import BaseModel

from app.agents.base import AnalysisContext, ModelTier
from app.agents.grounding import is_grounded, transcript_text
from app.agents.llm_agent import LLMAgent
from app.agents.names import CRM_EXTRACTION
from app.schemas.analysis import CrmExtraction

log = structlog.get_logger(__name__)


class CrmExtractionAgent(LLMAgent[CrmExtraction]):
    name: ClassVar[str] = CRM_EXTRACTION
    prompt_file: ClassVar[str] = "crm_extraction"
    prompt_version: ClassVar[str] = "crm_extraction.v1"
    output_schema: ClassVar[type[BaseModel]] = CrmExtraction
    # En çok alanı çıkaran ve yanlışın en pahalı olduğu agent; güçlü model kullanılır.
    model_tier: ClassVar[ModelTier] = "smart"

    def postprocess(self, output: CrmExtraction, ctx: AnalysisContext) -> CrmExtraction:
        """Konuşmada geçmeyen alıntıları ve boş alanlara ait alıntıları çıkarır.

        Alanın kendisine dokunulmaz; yalnızca kanıt olarak gösterilecek alıntı temizlenir.
        """
        transcript = transcript_text(ctx.segments)
        kept: dict[str, str] = {}
        for field, quote in output.evidence.items():
            if getattr(output, field) is None:
                reason = "alan boş"
            elif not is_grounded(quote, transcript):
                reason = "alıntı konuşmada geçmiyor"
            else:
                kept[field] = quote
                continue
            log.info("crm_extraction.evidence_dropped", field=field, reason=reason)
        return output.model_copy(update={"evidence": kept})

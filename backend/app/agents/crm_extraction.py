"""CRM Bilgi Çıkarım Agent'ı (#18).

Görüşmeden CRM kaydı önerisinin 7 alanını çıkarır: müşteri talebi, lokasyon, problem, hizmet
biçimi, aciliyet, potansiyel iş, sonraki aksiyon. Hocanın "çağrıdan CRM kaydı" işinin kalbidir.
"""

from typing import ClassVar

import structlog
from pydantic import BaseModel

from app.agents.base import AnalysisContext, ModelTier
from app.agents.grounding import is_grounded, normalize, transcript_text
from app.agents.llm_agent import LLMAgent, flagged_segments
from app.agents.names import CRM_EXTRACTION
from app.agents.terms import same_place
from app.schemas.analysis import CrmExtraction

log = structlog.get_logger(__name__)


def _copies_from(value: str, bad: str, good: str, run: int = 4) -> bool:
    words = normalize(value).split()
    for i in range(len(words) - run + 1):
        chunk = " ".join(words[i : i + run])
        if is_grounded(chunk, bad) and not is_grounded(chunk, good):
            return True
    return False


class CrmExtractionAgent(LLMAgent[CrmExtraction]):
    name: ClassVar[str] = CRM_EXTRACTION
    prompt_file: ClassVar[str] = "crm_extraction"
    prompt_version: ClassVar[str] = "crm_extraction.v3"
    output_schema: ClassVar[type[BaseModel]] = CrmExtraction
    # En çok alanı çıkaran ve yanlışın en pahalı olduğu agent; güçlü model kullanılır.
    model_tier: ClassVar[ModelTier] = "smart"

    def postprocess(self, output: CrmExtraction, ctx: AnalysisContext) -> CrmExtraction:
        """Konuşmada geçmeyen alıntıları ve boş alanlara ait alıntıları çıkarır.

        Alanın kendisine dokunulmaz; yalnızca kanıt olarak gösterilecek alıntı temizlenir.
        """
        output = self._normalize_location(output, ctx)
        output = self._drop_tainted(output, ctx)
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

    @staticmethod
    def _drop_tainted(output: CrmExtraction, ctx: AnalysisContext) -> CrmExtraction:
        """Talimat içeren satırlardan türetilmiş alanı boşaltır (dolaylı injection, #274).

        Bir alan, kanıt alıntısı yalnızca işaretli satırda geçiyorsa ya da metni işaretli
        satırdan art arda 4 sözcük kopyalıyorsa (temiz satırlarda yoksa) "bulaşmış" sayılır.
        """
        flagged = flagged_segments(ctx.segments)
        if not flagged:
            return output
        bad = transcript_text([s for s in ctx.segments if s.idx in flagged])
        good = transcript_text([s for s in ctx.segments if s.idx not in flagged])
        update: dict[str, object] = {}
        evidence = dict(output.evidence)
        for field in set(type(output).model_fields) - {"evidence"}:
            value = getattr(output, field)
            if value is None:
                continue
            quote = evidence.get(field, "")
            tainted = bool(quote) and is_grounded(quote, bad) and not is_grounded(quote, good)
            if isinstance(value, str) and not tainted:
                tainted = _copies_from(value, bad, good)
            if tainted:
                log.warning("crm_extraction.tainted_field_dropped", field=field)
                update[field] = None
                evidence.pop(field, None)
        if not update:
            return output
        return output.model_copy(update={**update, "evidence": evidence})

    @staticmethod
    def _normalize_location(output: CrmExtraction, ctx: AnalysisContext) -> CrmExtraction:
        """Konumu santraldeki marina adıyla tutarlı yazar.

        - Çıkarılan konum aynı yeri anlatıyorsa ("Kalamış" / "Kalamış Marina") marina adı yazılır.
        - Görüşmede konum geçmiyorsa (alan boşsa) çağrı bilgisindeki marina kullanılır.
        - Görüşmede başka bir yer açıkça söyleniyorsa dokunulmaz.
        """
        marina = ctx.call_info.marina if ctx.call_info else None
        if not marina:
            return output
        if not output.location:
            return output.model_copy(update={"location": marina})
        if output.location != marina and same_place(output.location, marina):
            return output.model_copy(update={"location": marina})
        return output

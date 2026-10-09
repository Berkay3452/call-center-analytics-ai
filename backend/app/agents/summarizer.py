"""Özetleme Agent'ı (#20).

CRM kaydında ve çağrı detayında gösterilecek kısa görüşme özetini üretir. Özetin en fazla
3 cümle olması şemada doğrulanır; burada ek olarak özete kişisel veri sızmadığı kontrol edilir.
"""

import re
from typing import ClassVar

from pydantic import BaseModel

from app.agents.base import AnalysisContext, ModelTier
from app.agents.llm_agent import LLMAgent
from app.agents.names import SUMMARIZER
from app.schemas.analysis import CallSummary

# Maskelenmemiş kişisel veri izleri. Transkript zaten maskeli gelir; bu, LLM'in özete veri
# uydurmasına veya maskeyi atlatan bir veriyi taşımasına karşı ikinci bir emniyettir.
_PII_PATTERNS = {
    "e-posta adresi": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "IBAN": re.compile(r"\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE),
    # Telefon, T.C. kimlik no, kart no: boşluk/tire/parantezle ayrılmış en az 10 rakam.
    # Nokta ayırıcı sayılmaz; yoksa "15.10.2026 14:30" gibi tarihler yanlışlıkla yakalanır.
    "uzun numara (telefon/kimlik)": re.compile(r"(?:\+?\d[\s\-()]*){10,}"),
}
# Maskeli ifadeler ([İSİM], [TELEFON]...) özete taşınmamalı.
_MASK_TOKEN = re.compile(r"\[[A-ZÇĞİÖŞÜ_]+\]")


def find_personal_data(text: str) -> list[str]:
    """Metinde bulunan kişisel veri türlerini döner (yoksa boş liste)."""
    found = [kind for kind, pattern in _PII_PATTERNS.items() if pattern.search(text)]
    if _MASK_TOKEN.search(text):
        found.append("maskeli ifade")
    return found


class SummarizerAgent(LLMAgent[CallSummary]):
    name: ClassVar[str] = SUMMARIZER
    prompt_file: ClassVar[str] = "summarizer"
    prompt_version: ClassVar[str] = "summarizer.v1"
    output_schema: ClassVar[type[BaseModel]] = CallSummary
    # Kısa özet hafif bir iş; hızlı model yeterli.
    model_tier: ClassVar[ModelTier] = "fast"

    def postprocess(self, output: CallSummary, ctx: AnalysisContext) -> CallSummary:
        found = find_personal_data(" ".join([output.summary, *output.key_points]))
        if found:
            raise ValueError(
                f"Özette kişisel veri var ({', '.join(found)}). Bu bilgileri çıkarıp yeniden yaz."
            )
        return output

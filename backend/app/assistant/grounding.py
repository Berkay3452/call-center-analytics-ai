"""Kaynak kontrolü: cevaptaki her ifadenin dayandığı kayıt gerçekten var mı?

LLM'den gelen her ifade kaynak kimlikleriyle gelir. Burada yalnızca **bu soru için bulunan**
kayıtlara işaret eden ifadeler tutulur; kaynağı olmayan veya uydurma kimliğe işaret eden ifade
silinir. Hiç ifade kalmazsa asistan "bulamadım" der.
"""

from pydantic import BaseModel, Field

from app.assistant.retrieval import Passage
from app.schemas.assistant import SourceRef

NOT_FOUND_MESSAGE = (
    "Bu konuda kayıtlarda bilgi bulamadım. Daha fazla bilgi için Miço Usta servis "
    "ekibinizle iletişime geçebilirsiniz."
)


class Claim(BaseModel):
    text: str = Field(min_length=1, description="Tek bir bilgi içeren kısa ifade.")
    source_ids: list[str] = Field(
        default_factory=list, description="İfadenin dayandığı kayıt kimlikleri."
    )


class AnswerDraft(BaseModel):
    """Cevap üretici LLM'in çıktısı: kaynaklı ifadeler."""

    claims: list[Claim] = Field(default_factory=list)


def ground_draft(draft: AnswerDraft, passages: list[Passage]) -> tuple[str, list[SourceRef]] | None:
    """Kaynağı doğrulanan ifadelerden cevap ve kaynak listesi kurar; hiçbiri kalmazsa None."""
    known = {p.source.record_id: p.source for p in passages}
    kept: list[str] = []
    used: dict[str, SourceRef] = {}
    for claim in draft.claims:
        valid = [i for i in claim.source_ids if i in known]
        if not valid:
            continue  # kaynağı yok veya uydurma kimlik: ifade çıkarılır
        kept.append(claim.text.strip())
        for i in valid:
            used.setdefault(i, known[i])
    if not kept:
        return None
    return " ".join(kept), list(used.values())

"""Tekne karnesi araması: servis kayıtları ve usta notlarında arama.

SAHTE (#22): basit kelime eşleşmesi. Gerçek hibrit arama (vektör + tam metin, RRF) #26'da
gelecek; fonksiyon imzası aynı kalır. Kurallar araçlarla aynıdır: `owner_id` zorunlu ve
yalnızca o sahibin kayıtları aranır.
"""

from dataclasses import dataclass

from app.agents.grounding import normalize
from app.assistant.tools import require_owner  # yetki kontrolü tek yerde yapılır
from app.schemas.assistant import SourceRef


@dataclass(frozen=True)
class Passage:
    """Aramadan dönen parça: cevabın dayanabileceği kayıt metni ve kaynak kartı."""

    source: SourceRef
    text: str


# Aramada anlam taşımayan sık kelimeler.
_STOP = frozenset(
    {"bir", "bu", "şu", "ve", "ile", "mi", "mı", "mu", "mü", "de", "da", "için", "ne", "neden"}
    | {"nasıl", "zaman", "hangi", "var", "yok", "son", "yapıldı", "yapmalıyım", "oldu", "olur"}
    | {"gerekir", "benim", "bana", "senin"}
)


def _tokens(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > 2 and t not in _STOP}


def search_boat_notes(owner_id: str, query: str, *, limit: int = 3) -> list[Passage]:
    """Sorguyla en çok kelime paylaşan kayıtlar (en iyiden başlayarak); eşleşme yoksa boş liste."""
    data = require_owner(owner_id)
    wanted = {t[:5] for t in _tokens(query)}  # kaba kök: ekleri (-ım, -ler...) yok sayar

    scored: list[tuple[int, Passage]] = []
    for note in data.notes:
        score = len(wanted & {t[:5] for t in _tokens(note.text)})
        if score:
            scored.append(
                (
                    score,
                    Passage(
                        source=SourceRef(
                            kind="boat_note",
                            record_id=note.record_id,
                            title=f"{note.on.strftime('%d.%m.%Y')} usta notu",
                            date=note.on,
                            excerpt=note.text,
                        ),
                        text=note.text,
                    ),
                )
            )
    scored.sort(key=lambda x: (-x[0], x[1].source.record_id))
    return [p for _, p in scored[:limit]]

"""Soruda adı geçen tekneyi çözümler (Ahmet Yılmaz'ın "Poyraz" ve "Yelkovan" tekneleri gibi).

Sahibin birden fazla teknesi olabilir. Soruda bir teknenin adı geçiyorsa araçlar ve arama o
tekneye daraltılır; geçmiyorsa tüm tekneler kapsanır. Soruda başkasının teknesinin adı geçerse
kayıt aranmaz: "bu tekne hesabınızda görünmüyor" denir (cevap başka sahibin verisini içermez).
"""

from dataclasses import dataclass

from app.agents.grounding import normalize
from app.assistant.tools import BoatRef

_MAX_SUFFIX = 4  # "yelkovan" + "in"/"dan"/"lari": Türkçe ek en fazla bu kadar harf
_MIN_FOREIGN_LEN = 4  # çok kısa adlar ("su") sıradan sözcüklerle karışmasın


@dataclass(frozen=True)
class BoatMatch:
    """`boat`: sorulan tekne (tek eşleşme); `foreign`: başkasının teknesi soruldu."""

    boat: BoatRef | None = None
    foreign: bool = False


def mentions_name(question_norm: str, name_norm: str) -> bool:
    """Normalize soruda tekne adı geçiyor mu? Son sözcükte iyelik/hal eki tolere edilir."""
    words = name_norm.split()
    tokens = question_norm.split()
    n = len(words)
    if n == 0 or len(tokens) < n:
        return False
    for i in range(len(tokens) - n + 1):
        window = tokens[i : i + n]
        head_ok = all(window[k] == words[k] for k in range(n - 1))
        last, word = window[-1], words[-1]
        if head_ok and (
            last == word or (last.startswith(word) and len(last) - len(word) <= _MAX_SUFFIX)
        ):
            return True
    return False


def resolve_boat(question: str, own: list[BoatRef], other_names: set[str]) -> BoatMatch:
    """Önce sahibin kendi tekneleri, yoksa başkasının tekne adları aranır."""
    text = normalize(question)
    matched = [b for b in own if mentions_name(text, normalize(b.name))]
    if len(matched) == 1:
        return BoatMatch(boat=matched[0])
    if matched:  # birden fazla tekne adı geçti: daraltma, hepsini kapsa
        return BoatMatch()
    own_names = {normalize(b.name) for b in own}
    for name in other_names:
        if len(name) >= _MIN_FOREIGN_LEN and name not in own_names and mentions_name(text, name):
            return BoatMatch(foreign=True)
    return BoatMatch()


def foreign_boat_reply(own: list[BoatRef]) -> str:
    """Başkasının teknesi sorulduğunda: sahibin kendi teknelerini hatırlatan nazik ret."""
    names = ", ".join(b.name for b in own)
    hint = f" Kayıtlı tekneleriniz: {names}." if names else ""
    return "Sorduğunuz tekne hesabınızda görünmüyor, bu yüzden bilgi veremem." + hint

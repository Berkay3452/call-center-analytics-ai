"""STT alan düzeltme sözlüğü (#330): sistematik yanlış yazımları ucuzca düzeltir.

Model hatası ayardan sonra kalan, **Türkçe'de karşılığı olmayan** yazımlar (ör. `generator` ->
`jeneratör`, `exoz` -> `egzoz`) bir sözlükle düzeltilir. Gerçek Türkçe sözcüklere dönüşen hatalar
(`akı`, `delil`, `buza`) bilerek sözlükte yoktur: bağlam olmadan doğru kelimeyi bozarlar.

Kurallar:
- Yalnız tam sözcük eşleşir (`marina` içindeki `ari` gibi parçalar değişmez); büyük/küçük harf
  korunur ("Generator" -> "Jeneratör", "GENERATOR" -> "JENERATÖR").
- `ek: true` kuralda yanlış sözcüğün **önü** eşleşir ve Türkçe ek korunur ("exozdan" -> "egzozdan").
- Tek geçiş; kuralların çıktısı başka kuralla yeniden değiştirilmez.
- Sıra: STT çıktısı -> düzeltme -> maskeleme (`store_segments`). Düzeltme yalnız alan sözcüklerine
  dokunur, kişisel veriye dokunmaz; metni günlüğe yazmaz.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RULES_PATH = Path(__file__).with_name("duzeltme_sozlugu.json")

Corrector = Callable[[str], str]


@dataclass(frozen=True)
class Rule:
    yanlis: str
    dogru: str
    ek: bool = False


def _tr_upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


def _tr_capitalize(text: str) -> str:
    return _tr_upper(text[:1]) + text[1:] if text else text


def load_rules(path: Path) -> list[Rule]:
    """Kural dosyasını okur ve doğrular (boş, kendine eşit ya da tekrarlı kural hatadır)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    rules: list[Rule] = []
    seen: set[str] = set()
    for item in raw["kurallar"]:
        rule = Rule(
            yanlis=item["yanlis"].strip().lower(),
            dogru=item["dogru"].strip().lower(),
            ek=bool(item.get("ek", False)),
        )
        if not rule.yanlis or not rule.dogru or rule.yanlis == rule.dogru:
            raise ValueError(f"Geçersiz düzeltme kuralı: {item!r}")
        if " " in rule.yanlis:
            raise ValueError(f"Düzeltme kuralı tek sözcük olmalı: {item!r}")
        if rule.yanlis in seen:
            raise ValueError(f"Yinelenen düzeltme kuralı: {rule.yanlis!r}")
        seen.add(rule.yanlis)
        rules.append(rule)
    return rules


class Duzeltici:
    """Kural listesini tek regex geçişiyle uygular; örnek, `Duzeltici(rules)("metin")`."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = {r.yanlis: r for r in rules}
        if rules:
            # Uzun kural önce: "exoz" ve "exozdan" gibi örtüşmede en uzun eşleşme kazanır.
            words = sorted(self._rules, key=len, reverse=True)
            self._pattern: re.Pattern[str] | None = re.compile(
                r"(?<!\w)(" + "|".join(re.escape(w) for w in words) + r")(\w*)",
                re.IGNORECASE,
            )
        else:
            self._pattern = None

    def __call__(self, text: str) -> str:
        if self._pattern is None or not text:
            return text
        return self._pattern.sub(self._replace, text)

    def _replace(self, match: re.Match[str]) -> str:
        word, rest = match.group(1), match.group(2)
        rule = self._rules[word.lower()]
        if rest and not rule.ek:
            return match.group(0)  # tam sözcük değil: dokunma
        fixed = rule.dogru
        if len(word) > 1 and word.isupper():
            fixed = _tr_upper(fixed)
        elif word[:1].isupper():
            fixed = _tr_capitalize(fixed)
        return fixed + rest


def build_corrector(enabled: bool = True, extra_file: str | Path | None = None) -> Corrector | None:
    """Ayarlardan düzeltici kurar; kapalıysa `None`. `extra_file` varsayılan kurallara eklenir."""
    if not enabled:
        return None
    rules = load_rules(DEFAULT_RULES_PATH)
    if extra_file:
        known = {r.yanlis for r in rules}
        rules += [r for r in load_rules(Path(extra_file)) if r.yanlis not in known]
    return Duzeltici(rules)

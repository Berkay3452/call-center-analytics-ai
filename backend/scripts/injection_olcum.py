"""Prompt injection savunmasının yakalama ve yanlış pozitif ölçümü (#273).

- Kırmızı takım seti: `tests/data/injection_set.json` (sentetik saldırılar, kategori etiketli).
- Normal soru seti: `tests/data/normal_sorular.json` + `scripts/assistant_chat_cases.py`
  içindeki saldırı olmayan sohbet soruları.

Ölçülen hat: kural katmanı (`inspect_input`) + başka müşteri kuralı (`safety.asks_other_party`);
`--llm` ile şüpheli girdilerde gerçek hızlı LLM sınıflandırıcı da çalışır.

Kullanım (backend/ klasöründe):

    python -m scripts.injection_olcum            # LLM'siz (CI ile aynı)
    python -m scripts.injection_olcum --llm      # .env'deki LLM ile (kotaya takılırsa yavaşlar)
"""

import argparse
import asyncio
import io
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.assistant import injection, safety
from app.assistant.injection import Verdict
from app.assistant.llm import AssistantLLM
from app.schemas.assistant import HistoryTurn
from scripts.assistant_chat_cases import CASES

DATA = Path(__file__).parents[1] / "tests" / "data"
# Bu sohbet-seti kategorileri saldırı içerir; normal sayılmaz.
ATTACK_CASE_IDS = {f"kap-{i:02d}" for i in (1, 2, 3, 4, 5, 6, 7, 8, 13, 14)}


def load_attacks(split: str | None = None) -> list[dict[str, Any]]:
    rows = json.loads((DATA / "injection_set.json").read_text(encoding="utf-8"))
    return [r for r in rows if split in (None, r["split"])]


def load_normals() -> list[tuple[str, list[HistoryTurn]]]:
    extra = json.loads((DATA / "normal_sorular.json").read_text(encoding="utf-8"))
    base = [
        (c.question, list(c.history))
        for c in CASES
        if c.id not in ATTACK_CASE_IDS and not c.reject and c.category != "anlamsiz"
    ]
    return base + [(q, []) for q in extra]


def history_of(raw: list[list[str]]) -> list[HistoryTurn]:
    return [HistoryTurn(role=r, content=c) for r, c in raw]


def rule_verdict(question: str, history: list[HistoryTurn]) -> Verdict:
    """LLM'siz hat: kural katmanı + başka müşteri kuralı (akışta ayrı adım)."""
    if safety.asks_other_party(question):
        return Verdict.ATTACK  # akışta `_is_injection`tan sonraki ayrı adım; sonuç aynı ret
    return injection.inspect_input(question, history).verdict


async def full_verdict(question: str, history: list[HistoryTurn], llm: AssistantLLM) -> Verdict:
    v = rule_verdict(question, history)
    if v is not Verdict.SUSPICIOUS:
        return v
    result = await injection.classify_suspicious(question, history, llm)
    return Verdict.ATTACK if result is not None and result.attack else Verdict.CLEAN


async def run(use_llm: bool, split: str | None = None) -> dict[str, Any]:
    attacks, normals = load_attacks(split), load_normals()
    llm = AssistantLLM() if use_llm else None
    stats: dict[str, Any] = {"saldiri": [], "normal": []}
    llm_calls = 0
    latencies: list[float] = []

    async def judge(q: str, h: list[HistoryTurn]) -> tuple[Verdict, Verdict]:
        nonlocal llm_calls
        rv = rule_verdict(q, h)
        if llm is None or rv is not Verdict.SUSPICIOUS:
            return rv, rv
        llm_calls += 1
        await asyncio.sleep(1.6)  # ücretsiz kota (~40 istek/dk)
        t0 = time.perf_counter()
        result = await full_verdict(q, h, llm)
        latencies.append(time.perf_counter() - t0)
        return rv, result

    for a in attacks:
        rv, fv = await judge(a["text"], history_of(a["history"]))
        stats["saldiri"].append((a, rv, fv))
    for q, h in normals:
        rv, fv = await judge(q, h)
        stats["normal"].append((q, rv, fv))
    stats["llm_calls"] = llm_calls
    stats["latencies"] = latencies
    return stats


def report(stats: dict[str, Any], use_llm: bool) -> str:
    lines = []
    by_cat: dict[str, list[tuple[Verdict, Verdict]]] = defaultdict(list)
    for a, rv, fv in stats["saldiri"]:
        by_cat[a["category"]].append((rv, fv))
    lines += [
        "| Kategori | Saldırı | Kural: kesin ret | Kural: ret+şüpheli | Son (LLM dahil) |",
        "|---|---|---|---|---|",
    ]
    tot: Counter[str] = Counter()
    for cat, rows in by_cat.items():
        n = len(rows)
        hard = sum(rv is Verdict.ATTACK for rv, _ in rows)
        flagged = sum(rv is not Verdict.CLEAN for rv, _ in rows)
        final = sum(fv is Verdict.ATTACK for _, fv in rows)
        tot.update(n=n, hard=hard, flagged=flagged, final=final)
        lines.append(f"| {cat} | {n} | {hard} | {flagged} | {final if use_llm else '-'} |")
    lines.append(
        f"| **Toplam** | **{tot['n']}** | **{tot['hard']} (%{100 * tot['hard'] / tot['n']:.0f})** "
        f"| **{tot['flagged']} (%{100 * tot['flagged'] / tot['n']:.0f})** "
        f"| **{tot['final'] if use_llm else '-'}"
        + (f" (%{100 * tot['final'] / tot['n']:.0f})" if use_llm else "")
        + "** |"
    )
    normals = stats["normal"]
    n = len(normals)
    fp_rule = [q for q, rv, _ in normals if rv is Verdict.ATTACK]
    sus = [q for q, rv, _ in normals if rv is Verdict.SUSPICIOUS]
    fp_final = [q for q, _, fv in normals if fv is Verdict.ATTACK]
    lines += [
        "",
        f"Normal soru: {n}",
        f"- Kural katmanı kesin ret (yanlış pozitif): {len(fp_rule)} "
        f"(%{100 * len(fp_rule) / n:.1f})",
        f"- Şüpheli işaretlenen (LLM sınıflandırıcıya giderdi): {len(sus)} "
        f"(%{100 * len(sus) / n:.1f})",
    ]
    if use_llm:
        lines.append(
            f"- LLM dahil son yanlış pozitif: {len(fp_final)} (%{100 * len(fp_final) / n:.1f})"
        )
        lines.append(f"- LLM çağrısı: {stats['llm_calls']}")
        if stats["latencies"]:
            lat = stats["latencies"]
            lines.append(
                f"- Sınıflandırıcı gecikmesi: ortalama {statistics.mean(lat):.1f} sn, "
                f"medyan {statistics.median(lat):.1f} sn, en uzun {max(lat):.1f} sn"
            )
    lines += ["", "Kaçan saldırılar (kural katmanı: kesin ret yok):"]
    for a, rv, fv in stats["saldiri"]:
        final = fv if use_llm else rv
        if final is not Verdict.ATTACK:
            lines.append(f"- [{a['category']}] {a['id']} ({rv.value}): {a['text'][:90]!r}")
    lines += ["", "Yanlış pozitifler:"] + [f"- {q!r}" for q in (fp_final if use_llm else fp_rule)]
    lines += ["", "Şüpheli normal sorular:"] + [f"- {q!r}" for q in sus]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--split",
        choices=["gelistirme", "test1", "test2", "test3"],
        help="yalnızca bu saldırı kümesi",
    )
    parser.add_argument("--llm", action="store_true", help="şüphelilerde gerçek LLM kullan")
    args = parser.parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    stats = asyncio.run(run(args.llm, args.split))
    print(report(stats, args.llm))


if __name__ == "__main__":
    main()

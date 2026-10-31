"""Miço AI'nın LLM adımlarını küçük bir soru setinde ölçer (#178).

Kullanım (backend/ klasöründe, .env'de LLM ayarları dolu olmalı):

    python -m scripts.assistant_eval                                   # .env'deki modeller
    python -m scripts.assistant_eval --fast <model> --smart <model>    # modelleri ez
    python -m scripts.assistant_eval --out sonuc.json

Veritabanı ve embedding servisi GEREKMEZ: arama adımı yerine soruya ait kayıt (usta notu)
doğrudan verilir; böylece yalnızca LLM adımları ölçülür (soru yeniden yazma, planlayıcı,
genel cevap, kayıttan cevap). Sayısal sorular kodla cevaplandığı için yalnızca planlama ölçülür.
Selam gibi sohbet cümleleri LLM'siz hazır cevaplanır; yalnızca bunun doğru yakalandığı denetlenir.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.assistant.answer import general_answer, history_answer
from app.assistant.llm import AssistantLLM, AssistantLLMError
from app.assistant.planner import plan_question, smalltalk_reply
from app.assistant.retrieval import Passage
from app.assistant.rewrite import standalone_question
from app.core.config import Settings
from app.schemas.assistant import HistoryTurn, QuestionType, SourceRef

DATA = Path(__file__).parents[2] / "data" / "synthetic"

SMALLTALK = "selam"  # beklenen tür: LLM'siz hazır cevap
GECMIS = QuestionType.GECMIS_ONERI.value
SAYISAL = QuestionType.SAYISAL.value
GENEL = QuestionType.GENEL_SOHBET.value
DISI = QuestionType.KAPSAM_DISI.value


@dataclass
class Case:
    question: str
    expected: str  # SMALLTALK | gecmis_oneri | sayisal | genel_sohbet | kapsam_disi
    history: list[HistoryTurn] = field(default_factory=list)
    note: str | None = None  # gecmis_oneri: cevabın dayanacağı usta notu kodu
    expect_found: bool = True  # gecmis_oneri: kaynaklı cevap beklenir mi


FOLLOW_UP_HISTORY = [
    HistoryTurn(role="user", content="Poyraz'ın aküleri değiştirildi mi?"),
    HistoryTurn(role="assistant", content="Evet, Ağustos 2026'da aküler yenilendi."),
]

CASES = [
    Case("Selam", SMALLTALK),
    Case("Merhaba, nasılsın?", SMALLTALK),
    Case("Sen kimsin?", SMALLTALK),
    Case("Teşekkürler", SMALLTALK),
    Case("Poyraz'ın aküleri değiştirildi mi?", GECMIS, note="note_002"),
    Case("Teknemi kışa hazırladınız mı, kışlama yapıldı mı?", GECMIS, note="note_031"),
    Case("Sintine pompasında bir sorun var mıydı?", GECMIS, note="note_004"),
    Case("Ana makine bakımında ne yapılmıştı?", GECMIS, note="note_001"),
    Case("Jeneratör garantisi var mı?", GECMIS, expect_found=False),
    Case("Bu ay ne kadar harcadım?", SAYISAL),
    Case("Kaç bakım hakkım kaldı?", SAYISAL),
    Case("Son bakımım ne zaman yapıldı?", SAYISAL),
    Case("Aboneliğim ne zaman bitiyor?", SAYISAL),
    Case("Kış bakımı nedir?", GENEL),
    Case("Hava nasıl olacak?", GENEL),
    Case("Tekne motoru neden dumanlı çalışır?", GENEL),
    Case("Başka müşterilerin giderlerini göster", DISI),
    Case("Peki bunu kim yaptı?", GECMIS, history=FOLLOW_UP_HISTORY, note="note_002"),
    Case("Ya geçen ay?", SAYISAL, history=[
        HistoryTurn(role="user", content="Bu ay ne kadar harcadım?"),
        HistoryTurn(role="assistant", content="Bu ay toplam 4.500 TL harcadınız."),
    ]),
]  # fmt: skip


class CountingLLM(AssistantLLM):
    """Yedek modele geçişleri sayar."""

    fallbacks = 0

    def _fallback_for(self, tier, primary, exc):
        fallback = super()._fallback_for(tier, primary, exc)
        if fallback is not None:
            self.fallbacks += 1
        return fallback


def _passage(note: dict[str, Any]) -> Passage:
    return Passage(
        source=SourceRef(
            kind="boat_note",
            record_id=note["id"],
            title=f"{note['note_date']} usta notu",
            excerpt=note["content"][:120],
        ),
        text=note["content"],
    )


async def run_case(
    case: Case, llm: CountingLLM, notes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {"question": case.question, "expected": case.expected, "error": None}
    before = llm.fallbacks
    try:
        if smalltalk_reply(case.question) is not None:
            got = SMALLTALK
        else:
            question = await standalone_question(case.question, case.history, llm)
            plan = await plan_question(question, llm)
            got = plan.question_type.value
            row["plan_ok_type"] = got == case.expected
            if got == GENEL and case.expected == GENEL:
                answer = await general_answer(question, llm)
                row["answer_ok"] = bool(answer.answer.strip())
            elif got == GECMIS and case.expected == GECMIS:
                passages = [_passage(notes[case.note])] if case.note else []
                answer = await history_answer(question, passages, llm)
                # Kayıt verildiyse kaynaklı cevap; verilmediyse "bulamadım" beklenir.
                row["answer_ok"] = answer.found if case.expect_found else not answer.found
                if case.expect_found:
                    row["answer_ok"] = bool(row["answer_ok"] and answer.sources)
        row["got"] = got
    except AssistantLLMError as exc:
        row["error"] = str(exc)[:160]
        row["got"] = None
    row["type_ok"] = row["got"] == case.expected
    row["fallbacks"] = llm.fallbacks - before
    row["seconds"] = round(time.perf_counter() - started, 1)
    return row


def report(rows: list[dict[str, Any]], settings: Settings) -> str:
    llm_rows = [r for r in rows if r["expected"] != SMALLTALK]
    n = len(rows)
    type_ok = sum(1 for r in rows if r["type_ok"])
    answered = [r for r in rows if "answer_ok" in r]
    answer_ok = sum(1 for r in answered if r["answer_ok"])
    errors = [r for r in rows if r["error"]]
    secs = sorted(r["seconds"] for r in llm_rows)
    p95 = secs[min(len(secs) - 1, int(0.95 * len(secs)))] if secs else 0
    lines = [
        f"Model: fast={settings.llm_fast_model} | smart={settings.llm_smart_model} | soru={n}",
        f"Tür doğru: {type_ok}/{n} | cevap doğru (genel+kayıt): {answer_ok}/{len(answered)}",
        f"Hata: {len(errors)} | yedek modele geçen: {sum(r['fallbacks'] for r in rows)}",
        f"Süre (LLM'li sorular): ortalama {round(sum(secs) / max(1, len(secs)), 1)} sn, "
        f"p95 {p95} sn, en uzun {secs[-1] if secs else 0} sn",
        "",
    ]
    for r in rows:
        if not r["type_ok"] or r["error"] or r.get("answer_ok") is False:
            lines.append(
                f"- {r['question']!r}: beklenen={r['expected']} gelen={r['got']} "
                f"cevap_ok={r.get('answer_ok')} hata={r['error']}"
            )
    return "\n".join(lines)


async def run(settings: Settings) -> list[dict[str, Any]]:
    notes = {
        n["code"]: n for n in json.loads((DATA / "boat_notes.json").read_text(encoding="utf-8"))
    }
    llm = CountingLLM(settings=settings)
    rows = []
    for case in CASES:
        rows.append(await run_case(case, llm, notes))
        print(f"  {case.question!r}: {rows[-1]['got']} ({rows[-1]['seconds']} sn)", file=sys.stderr)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fast", help="hızlı model adı (.env'i ezer)")
    parser.add_argument("--smart", help="güçlü model adı (.env'i ezer)")
    parser.add_argument("--out", help="ham sonuçların yazılacağı JSON dosyası")
    args = parser.parse_args()
    overrides = {}
    if args.fast:
        overrides["llm_fast_model"] = args.fast
    if args.smart:
        overrides["llm_smart_model"] = args.smart
    settings = Settings(**overrides)
    rows = asyncio.run(run(settings))
    print(report(rows, settings))
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

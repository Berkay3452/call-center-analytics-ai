"""STT alan düzeltme sözlüğü (#330): doğru düzeltir, doğru kelimeyi bozmaz."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.stt.base import SttSegment
from app.stt.duzeltme import (
    DEFAULT_RULES_PATH,
    Duzeltici,
    Rule,
    build_corrector,
    load_rules,
)
from app.stt.providers import FasterWhisperTranscriber
from app.stt.registry import build_transcriber

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC = ROOT / "data" / "synthetic"


@pytest.fixture(scope="module")
def fix() -> Duzeltici:
    return Duzeltici(load_rules(DEFAULT_RULES_PATH))


def test_default_rules_are_valid_and_unique() -> None:
    rules = load_rules(DEFAULT_RULES_PATH)
    assert len(rules) >= 8
    assert len({r.yanlis for r in rules}) == len(rules)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("generator arızalı", "jeneratör arızalı"),
        ("Generator arızalı", "Jeneratör arızalı"),
        ("GENERATOR", "JENERATÖR"),
        ("generatörü çalıştır", "jeneratörü çalıştır"),
        ("exozdan duman çıkıyor", "egzozdan duman çıkıyor"),
        ("çekme de winch bozuk", "çekme de vinç bozuk"),
        ("Malina'da buluşalım", "Marina'da buluşalım"),
        ("akdemiz'de", "akdeniz'de"),
        ("aküllerini değiştir", "akülerini değiştir"),
        ("dimini yırtılmış", "bimini yırtılmış"),
    ],
)
def test_known_misspellings_are_fixed(fix: Duzeltici, raw: str, expected: str) -> None:
    assert fix(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "akı ve delil buza bora",  # gerçek Türkçe sözcükler: sözlükte yok
        "jeneratör ve egzoz sorunsuz",
        "Marina'da tekne var",
        "animalina kelimesi",  # gövde içinde geçmesi tam sözcük sayılmaz
        "supermalina",
        "",
    ],
)
def test_correct_words_are_untouched(fix: Duzeltici, text: str) -> None:
    assert fix(text) == text


def test_non_ek_rule_does_not_match_longer_word() -> None:
    fix = Duzeltici([Rule("dimini", "bimini")])
    assert fix("diminiler") == "diminiler"  # `ek` yok: tam sözcük değil, dokunma
    assert fix("dimini.") == "bimini."


def test_overlapping_rules_use_longest_match() -> None:
    fix = Duzeltici([Rule("ex", "eks", ek=True), Rule("exoz", "egzoz", ek=True)])
    assert fix("exozdan") == "egzozdan"


def test_single_pass_does_not_chain() -> None:
    fix = Duzeltici([Rule("a1", "b1"), Rule("b1", "c1")])
    assert fix("a1") == "b1"


def test_empty_rule_set_is_identity() -> None:
    assert Duzeltici([])("generator") == "generator"


def test_no_false_positives_on_reference_corpus(fix: Duzeltici) -> None:
    """Doğru yazılmış sentetik metinlerde (100 görüşme, usta notları) hiçbir şey değişmemeli."""
    texts: list[str] = []
    for path in sorted((SYNTHETIC / "calls").glob("*.json")):
        texts += [t["text"] for t in json.loads(path.read_text(encoding="utf-8"))["turns"]]
    for note in json.loads((SYNTHETIC / "boat_notes.json").read_text(encoding="utf-8")):
        texts += [str(v) for v in note.values() if isinstance(v, str)]
    assert len(texts) > 1000
    changed = [t for t in texts if fix(t) != t]
    assert not changed, f"Sözlük doğru metni bozdu: {changed[:3]}"


def test_load_rules_rejects_bad_files(tmp_path: Path) -> None:
    def write(rules: list[dict[str, object]]) -> Path:
        path = tmp_path / "r.json"
        path.write_text(json.dumps({"kurallar": rules}), encoding="utf-8")
        return path

    with pytest.raises(ValueError, match="Geçersiz"):
        load_rules(write([{"yanlis": "x", "dogru": "x"}]))
    with pytest.raises(ValueError, match="tek sözcük"):
        load_rules(write([{"yanlis": "iki kelime", "dogru": "x"}]))
    with pytest.raises(ValueError, match="Yinelenen"):
        load_rules(write([{"yanlis": "x", "dogru": "y"}, {"yanlis": "X", "dogru": "z"}]))


def test_build_corrector_disabled_and_extra_file(tmp_path: Path) -> None:
    assert build_corrector(enabled=False) is None
    extra = tmp_path / "ek.json"
    extra.write_text(
        json.dumps({"kurallar": [{"yanlis": "zzmotor", "dogru": "motor"}]}), encoding="utf-8"
    )
    fix = build_corrector(True, extra)
    assert fix is not None
    assert fix("zzmotor ve generator") == "motor ve jeneratör"
    # Varsayılan kuralı geçersiz kılamaz: aynı yanlış yazım ek dosyada yok sayılır.
    extra.write_text(
        json.dumps({"kurallar": [{"yanlis": "generator", "dogru": "başka"}]}), encoding="utf-8"
    )
    fix2 = build_corrector(True, extra)
    assert fix2 is not None
    assert fix2("generator") == "jeneratör"


def test_registry_wires_corrector_from_settings() -> None:
    on = build_transcriber(Settings(stt_provider="faster_whisper"))
    off = build_transcriber(Settings(stt_provider="faster_whisper", stt_correction_enabled=False))
    assert isinstance(on, FasterWhisperTranscriber) and on.corrector is not None
    assert isinstance(off, FasterWhisperTranscriber) and off.corrector is None


class _Seg:
    def __init__(self, text: str) -> None:
        self.start, self.end, self.text, self.words = 0.0, 1.0, text, None


class _Info:
    language = "tr"
    duration = 1.0


class _Model:
    def transcribe(self, audio: object, **kwargs: object) -> tuple[list[_Seg], _Info]:
        return [_Seg("generator arızalı"), _Seg("tamam")], _Info()


async def test_transcriber_applies_corrections_to_segments(tmp_path: Path) -> None:
    fix = Duzeltici(load_rules(DEFAULT_RULES_PATH))
    transcriber = FasterWhisperTranscriber("small", model=_Model(), corrector=fix)
    result = await transcriber.transcribe(tmp_path / "a.wav")
    assert [s.text for s in result.segments] == ["jeneratör arızalı", "tamam"]
    assert all(isinstance(s, SttSegment) for s in result.segments)
    plain = FasterWhisperTranscriber("small", model=_Model())
    assert (await plain.transcribe(tmp_path / "a.wav")).segments[0].text == "generator arızalı"

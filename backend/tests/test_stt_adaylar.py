"""STT aday modelleri ve karşılaştırma sağlayıcıları (#331)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.core.config import Settings
from app.stt.adaylar import CANDIDATES
from app.stt.benchmark_providers import HfCtcTranscriber
from app.stt.registry import build_transcriber
from scripts.stt_aday_kosusu import summarize_file, table
from scripts.stt_benchmark import candidate_overrides


def test_candidates_are_consistent() -> None:
    assert {"small", "medium", "large-v3", "large-v3-turbo", "xlsr-tr"} <= set(CANDIDATES)
    for name, c in CANDIDATES.items():
        assert c.name == name
        assert c.license and c.note and c.timestamps
        assert c.provider in ("faster_whisper", "hf_ctc", "openai_compatible")
    # Üretim varsayılanı bir adaydır, ama adaylar üretim ayarını değiştirmez.
    assert Settings().whisper_model in {c.model for c in CANDIDATES.values()}
    external = [c.name for c in CANDIDATES.values() if c.external]
    assert external == ["groq-large-v3"]


def test_candidate_overrides_local(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, overrides = candidate_overrides("large-v3-tr")
    assert provider == "faster_whisper"
    assert overrides == {"whisper_model": "oguzhangokboru/whisper-large-v3-tr"}
    assert candidate_overrides("xlsr-tr")[0] == "hf_ctc"


def test_external_candidate_needs_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STT_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="STT_API_KEY"):
        candidate_overrides("groq-large-v3")
    monkeypatch.setenv("STT_API_KEY", "test-anahtar")
    provider, overrides = candidate_overrides("groq-large-v3")
    assert provider == "openai_compatible"
    assert overrides["stt_allow_external"] is True


def test_unknown_candidate_exits() -> None:
    with pytest.raises(SystemExit, match="Bilinmeyen aday"):
        candidate_overrides("yok")


def test_external_provider_stays_closed_by_default() -> None:
    """Aday altyapısı `STT_ALLOW_EXTERNAL=false` korumasını gevşetmez."""
    with pytest.raises(ValueError, match="Harici STT kapalı"):
        build_transcriber(Settings(), "openai_compatible")


def test_registry_builds_hf_ctc_with_corrector() -> None:
    transcriber = build_transcriber(Settings(whisper_model="org/model"), "hf_ctc")
    assert isinstance(transcriber, HfCtcTranscriber)
    assert transcriber.model_id == "org/model"
    assert transcriber.corrector is not None


class _FakePipe:
    def __call__(self, inputs: dict[str, object], **kwargs: object) -> dict[str, object]:
        assert kwargs["return_timestamps"] == "word"
        assert inputs["sampling_rate"] == 16_000
        return {
            "text": "generator çalışmıyor tamam",
            "chunks": [
                {"text": "generator", "timestamp": (0.0, 0.5)},
                {"text": "çalışmıyor", "timestamp": (0.6, 1.2)},
                {"text": "tamam", "timestamp": (3.0, 3.4)},  # uzun duraklamadan sonra
            ],
        }


async def test_hf_ctc_builds_segments_at_pauses_and_corrects() -> None:
    from app.stt.duzeltme import build_corrector

    transcriber = HfCtcTranscriber("org/model", corrector=build_corrector(), pipe=_FakePipe())
    result = await transcriber.transcribe_array(np.zeros(16_000 * 4, dtype="float32"))
    assert [s.text for s in result.segments] == ["jeneratör çalışmıyor", "tamam"]
    assert result.segments[1].start_ms == 3000
    assert result.duration_sec == 4.0
    assert result.model == "hf_ctc/org/model"


def test_hf_ctc_without_transformers_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "transformers":
            raise ImportError("yok")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from app.stt.base import SttError

    with pytest.raises(SttError, match="torch ve transformers"):
        HfCtcTranscriber("org/model")._get_pipe()


def test_summary_table(tmp_path: Path) -> None:
    rows = [
        {
            "file": "a.wav",
            "wer": 0.2,
            "wer_rep": 0.1,
            "wer_customer": 0.3,
            "duration_s": 100.0,
            "processing_s": 30.0,
            "peak_mb": 1900,
            "load_s": 4.0,
            "terms": {"parca": [8, 10], "yer": [4, 5]},
        },
        {"file": "b.wav", "error": "bozuk"},
    ]
    path = tmp_path / "x.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    summary = summarize_file(path)
    assert summary is not None
    assert summary["terms"] == (12, 15)
    assert summary["files"] == 1
    text = table({"x": summary, "groq-large-v3": "anahtar yok (ölçülmedi)"})
    assert "%20.0" in text and "%80.0 (12/15)" in text and "0.30" in text
    assert "anahtar yok" in text

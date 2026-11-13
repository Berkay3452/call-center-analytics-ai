"""Mono kayıtta metin tabanlı konuşmacı ayrımı (app/stt/diarize.py). LLM sahtelenir."""

import json
from itertools import pairwise
from pathlib import Path

import pytest

from app.assistant.llm import AssistantLLM, AssistantLLMError
from app.stt.base import SttSegment, TranscriptionResult
from app.stt.diarize import label_speakers, split_sentences
from app.stt.pipeline import merge_turns, transcribe_call
from tests.llm_fakes import scripted


def seg(start: int, end: int, text: str, speaker: str | None = None) -> SttSegment:
    return SttSegment(start_ms=start, end_ms=end, text=text, speaker=speaker)


TEXT = "Miço Usta, iyi günler. Merhaba, motorum çalışmıyor. Tekne adı nedir? Rüzgar."


def test_split_sentences_shares_time_by_length() -> None:
    parts = split_sentences([seg(0, 4000, TEXT)])
    assert [p.text for p in parts] == [
        "Miço Usta, iyi günler.",
        "Merhaba, motorum çalışmıyor.",
        "Tekne adı nedir?",
        "Rüzgar.",
    ]
    assert parts[0].start_ms == 0 and parts[-1].end_ms == 4000
    assert all(a.end_ms == b.start_ms for a, b in pairwise(parts))


async def test_labels_sentences_and_merges_into_turns() -> None:
    llm = AssistantLLM(
        model=scripted(json.dumps({"labels": ["rep", "customer", "rep", "customer"]}))
    )
    labeled = await label_speakers([seg(0, 4000, TEXT)], llm)
    turns = merge_turns(labeled)
    assert [t.speaker for t in turns] == ["rep", "customer", "rep", "customer"]
    assert turns[0].text == "Miço Usta, iyi günler."


async def test_consecutive_same_speaker_sentences_merge() -> None:
    llm = AssistantLLM(
        model=scripted(json.dumps({"labels": ["rep", "customer", "customer", "customer"]}))
    )
    turns = merge_turns(await label_speakers([seg(0, 4000, TEXT)], llm))
    assert [t.speaker for t in turns] == ["rep", "customer"]


async def test_length_mismatch_keeps_original() -> None:
    llm = AssistantLLM(model=scripted(json.dumps({"labels": ["rep", "customer"]})))
    original = [seg(0, 4000, TEXT)]
    assert await label_speakers(original, llm) == original


async def test_llm_error_keeps_original() -> None:
    llm = AssistantLLM(model=scripted(RuntimeError("kota")))
    original = [seg(0, 4000, TEXT)]
    assert await label_speakers(original, llm) == original


async def test_provider_known_speakers_are_not_overwritten() -> None:
    llm = AssistantLLM(model=scripted())  # çağrılırsa AssertionError
    known = [seg(0, 1000, "Merhaba.", "rep")]
    assert await label_speakers(known, llm) == known


def test_error_type_exported() -> None:
    assert issubclass(AssistantLLMError, RuntimeError)


class _Mono:
    name = "fake"

    async def transcribe(self, path: Path, *, language: str) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[seg(0, 4000, TEXT)], duration_sec=4.0, model="fake", language=language
        )


async def test_transcribe_call_uses_diarizer_for_mono(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    llm = AssistantLLM(
        model=scripted(json.dumps({"labels": ["rep", "customer", "rep", "customer"]}))
    )

    async def diarizer(segments: list[SttSegment]) -> list[SttSegment]:
        return await label_speakers(segments, llm)

    result = await transcribe_call(audio, _Mono(), layout="mono", diarizer=diarizer)  # type: ignore[arg-type]
    assert [t.speaker for t in result.turns] == ["rep", "customer", "rep", "customer"]


async def test_transcribe_call_without_diarizer_stays_single_turn(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    result = await transcribe_call(audio, _Mono(), layout="mono")  # type: ignore[arg-type]
    assert [t.speaker for t in result.turns] == ["unknown"]


@pytest.mark.parametrize("n", [0])
def test_empty(n: int) -> None:
    assert split_sentences([]) == []

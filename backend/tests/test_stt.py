"""STT altyapısı (#15): sağlayıcılar, konuşmacı ayrımı, birleştirme ve ölçütler.

Gerçek model indirilmez: faster-whisper ve API istemcisi sahtelenir. Stereo dosya testleri
`stt` ekstrası (faster-whisper) kuruluysa çalışır; gerçek model testi `RUN_STT_TESTS=1` ister.
"""

import os
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.stt.base import SttError, SttSegment, TranscriptionResult
from app.stt.metrics import cer, normalize, wer
from app.stt.pipeline import CallTranscription, merge_turns, transcribe_call
from app.stt.providers import (
    FasterWhisperTranscriber,
    OpenAICompatibleTranscriber,
    StubTranscriber,
)
from app.stt.registry import build_transcriber
from tests.conftest import make_settings

# --- Yardımcılar --------------------------------------------------------------------------


def seg(start: int, end: int, text: str, speaker: Any = None) -> SttSegment:
    return SttSegment(start_ms=start, end_ms=end, text=text, speaker=speaker)


class FakeTranscriber:
    """Dosya veya dizi alır; çağrıları kaydeder ve hazır sonuç döner."""

    name = "fake"

    def __init__(self, segments: list[SttSegment]) -> None:
        self.segments = segments
        self.calls: list[Any] = []

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        self.calls.append(audio_path)
        return TranscriptionResult(
            language=language, duration_sec=12.0, segments=self.segments, model="fake"
        )


def write_wav(path: Path, channels: int, seconds: float = 0.5) -> Path:
    frames = int(16_000 * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * frames * channels)
    return path


# --- Tur birleştirme ----------------------------------------------------------------------


def test_merge_turns_sorts_by_time_and_joins_same_speaker() -> None:
    turns = merge_turns(
        [
            seg(5000, 7000, "Hangi marina?", "rep"),
            seg(0, 2000, "Motor tekliyor", "customer"),
            seg(2000, 4000, "yakıt filtresi olabilir.", "customer"),
            seg(7500, 8000, "  ", "customer"),  # boş parça atlanır
        ]
    )

    assert [(t.speaker, t.text) for t in turns] == [
        ("customer", "Motor tekliyor yakıt filtresi olabilir."),
        ("rep", "Hangi marina?"),
    ]
    assert (turns[0].start_ms, turns[0].end_ms) == (0, 4000)


def test_merge_turns_marks_unknown_speaker() -> None:
    turns = merge_turns([seg(0, 1000, "Alo"), seg(1000, 2000, "Merhaba")])

    assert [(t.speaker, t.text) for t in turns] == [("unknown", "Alo Merhaba")]


def test_to_segments_maps_unknown_to_customer() -> None:
    result = CallTranscription(
        turns=merge_turns([seg(0, 1000, "Alo")]),
        duration_sec=1,
        model="x",
        layout="mono",
        processing_s=0.1,
    )

    (segment,) = result.to_segments()
    assert (segment.speaker, segment.start_ms, segment.end_ms) == ("customer", 0, 1000)


# --- Boru hattı: mono ve stereo -----------------------------------------------------------


async def test_transcribe_call_mono(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "c.wav", channels=1)
    fake = FakeTranscriber([seg(0, 1000, "Merhaba"), seg(1000, 2000, "teknem var")])

    result = await transcribe_call(audio, fake, layout="mono")

    assert [(t.speaker, t.text) for t in result.turns] == [("unknown", "Merhaba teknem var")]
    assert result.duration_sec == 12.0
    assert fake.calls == [audio]


async def test_transcribe_call_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SttError, match="Ses dosyası yok"):
        await transcribe_call(tmp_path / "yok.wav", FakeTranscriber([]))


async def test_stereo_layout_on_mono_file_falls_back_to_mono(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "c.wav", channels=1)
    fake = FakeTranscriber([seg(0, 1000, "Alo")])

    result = await transcribe_call(audio, fake, layout="stereo_rep_left")

    assert result.layout == "mono"
    assert len(fake.calls) == 1


async def test_stereo_channels_become_speakers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("numpy")
    import numpy as np

    from app.stt import pipeline

    audio = write_wav(tmp_path / "c.wav", channels=2)
    left, right = np.zeros(16_000, dtype="float32"), np.ones(8_000, dtype="float32") * 0.1
    monkeypatch.setattr(pipeline, "split_stereo", lambda path: (left, right))

    class ChannelFake(FakeTranscriber):
        async def transcribe(self, audio_path: Path, *, language: str = "tr") -> Any:
            self.calls.append(audio_path.name)
            texts = {
                "rep.wav": [seg(0, 1000, "Miço Usta, buyurun."), seg(3000, 4000, "Hangi marina?")],
                "customer.wav": [seg(1200, 2800, "Motor tekliyor.")],
            }
            return TranscriptionResult(
                language="tr", duration_sec=1, segments=texts[audio_path.name], model="fake"
            )

    fake = ChannelFake([])
    result = await transcribe_call(audio, fake, layout="stereo_rep_left")

    assert fake.calls == ["rep.wav", "customer.wav"]  # API sağlayıcısına kanal başına WAV
    assert [(t.speaker, t.text) for t in result.turns] == [
        ("rep", "Miço Usta, buyurun."),
        ("customer", "Motor tekliyor."),
        ("rep", "Hangi marina?"),
    ]
    assert result.duration_sec == 1.0  # uzun kanal: 16 000 örnek


async def test_stereo_rep_right_swaps_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.stt import pipeline

    audio = write_wav(tmp_path / "c.wav", channels=2)
    monkeypatch.setattr(pipeline, "split_stereo", lambda path: ("SOL", "SAĞ"))

    class ArrayFake:
        name = "array"

        def __init__(self) -> None:
            self.seen: list[Any] = []

        async def transcribe(self, audio_path: Path, *, language: str = "tr") -> Any:
            raise AssertionError("dizi destekleyen sağlayıcıya dosya gönderilmemeli")

        async def transcribe_array(self, audio: Any, *, language: str = "tr") -> Any:
            self.seen.append(audio)
            return TranscriptionResult(
                language="tr", duration_sec=1, segments=[seg(0, 10, audio)], model="a"
            )

    fake = ArrayFake()
    result = await transcribe_call(audio, fake, layout="stereo_rep_right")

    assert fake.seen == ["SAĞ", "SOL"]  # önce temsilci (sağ) kanalı
    assert {(t.speaker, t.text) for t in result.turns} == {("rep", "SAĞ"), ("customer", "SOL")}


def test_split_stereo_real_decoder(tmp_path: Path) -> None:
    pytest.importorskip("faster_whisper")
    from app.stt.pipeline import audio_channels, split_stereo

    audio = write_wav(tmp_path / "s.wav", channels=2, seconds=1.0)

    left, right = split_stereo(audio)

    assert audio_channels(audio) == 2
    assert len(left) == len(right) == 16_000


# --- Sağlayıcılar -------------------------------------------------------------------------


async def test_stub_reads_sidecar_transcript(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "call.wav", channels=1)
    audio.with_suffix(".txt").write_text(
        "Temsilci: Miço Usta, buyurun.\nMüşteri: Motor tekliyor.", encoding="utf-8"
    )

    result = await transcribe_call(audio, StubTranscriber())

    assert [(t.speaker, t.text) for t in result.turns] == [
        ("rep", "Miço Usta, buyurun."),
        ("customer", "Motor tekliyor."),
    ]
    assert result.model == "stub"


async def test_stub_without_sidecar_fails(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "call.wav", channels=1)

    with pytest.raises(SttError, match=r"call\.txt"):
        await StubTranscriber().transcribe(audio)


class _FakeWhisperModel:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.kwargs: dict[str, Any] = {}

    def transcribe(self, audio: Any, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.fail:
            raise RuntimeError("bozuk dosya")
        segments = iter(
            [
                SimpleNamespace(start=0.0, end=1.25, text=" Merhaba "),
                SimpleNamespace(start=1.25, end=1.5, text="  "),
                SimpleNamespace(start=1.5, end=3.0, text="motor tekliyor."),
            ]
        )
        return segments, SimpleNamespace(language="tr", duration=3.2)


async def test_faster_whisper_converts_segments(tmp_path: Path) -> None:
    model = _FakeWhisperModel()
    transcriber = FasterWhisperTranscriber("small", model=model)

    result = await transcriber.transcribe(tmp_path / "x.wav", language="tr")

    assert [(s.start_ms, s.end_ms, s.text) for s in result.segments] == [
        (0, 1250, "Merhaba"),
        (1500, 3000, "motor tekliyor."),
    ]
    assert result.duration_sec == 3.2
    assert result.model == "faster-whisper/small/int8"
    assert model.kwargs["language"] == "tr"
    assert model.kwargs["vad_filter"] is True


async def test_faster_whisper_errors_become_stt_errors(tmp_path: Path) -> None:
    transcriber = FasterWhisperTranscriber(model=_FakeWhisperModel(fail=True))

    with pytest.raises(SttError, match="bozuk dosya"):
        await transcriber.transcribe(tmp_path / "x.wav")


class _FakeAudioApi:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def _api_client(api: _FakeAudioApi) -> Any:
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=api))


async def test_openai_compatible_parses_verbose_json(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "c.wav", channels=1)
    api = _FakeAudioApi(
        SimpleNamespace(
            language="turkish",
            duration=4.0,
            text="Merhaba. Motor tekliyor.",
            segments=[
                SimpleNamespace(start=0.0, end=1.0, text=" Merhaba."),
                SimpleNamespace(start=1.0, end=4.0, text=" Motor tekliyor."),
            ],
        )
    )
    transcriber = OpenAICompatibleTranscriber(
        base_url="http://x", api_key="k", client=_api_client(api)
    )

    result = await transcriber.transcribe(audio)

    assert [s.text for s in result.segments] == ["Merhaba.", "Motor tekliyor."]
    assert result.duration_sec == 4.0
    assert api.kwargs["response_format"] == "verbose_json"
    assert api.kwargs["language"] == "tr"


async def test_openai_compatible_network_error_is_transient(tmp_path: Path) -> None:
    import openai

    audio = write_wav(tmp_path / "c.wav", channels=1)
    # İstek nesnesi olmadan bağlantı hatası (openai'nin httpx sürümüne bağlı kalmamak için).
    error = openai.APIConnectionError.__new__(openai.APIConnectionError)
    Exception.__init__(error, "bağlantı yok")
    transcriber = OpenAICompatibleTranscriber(
        base_url="http://x", api_key="k", client=_api_client(_FakeAudioApi(error=error))
    )

    with pytest.raises(SttError) as info:
        await transcriber.transcribe(audio)
    assert info.value.transient is True


async def test_openai_compatible_requires_key(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "c.wav", channels=1)

    with pytest.raises(SttError, match="STT_API_KEY"):
        await OpenAICompatibleTranscriber(base_url="http://x", api_key=None).transcribe(audio)


def test_registry_builds_configured_provider() -> None:
    settings = make_settings(stt_provider="faster_whisper", whisper_model="base")

    whisper = build_transcriber(settings)
    assert isinstance(whisper, FasterWhisperTranscriber)
    assert whisper.model_size == "base"
    assert whisper._model is None  # model ilk kullanımda yüklenir
    assert isinstance(build_transcriber(settings, "stub"), StubTranscriber)
    assert isinstance(build_transcriber(settings, "openai_compatible"), OpenAICompatibleTranscriber)
    with pytest.raises(ValueError, match="Bilinmeyen"):
        build_transcriber(settings, "deepgram")


# --- Ölçütler -----------------------------------------------------------------------------


def test_normalize_handles_turkish_case_masks_and_punctuation() -> None:
    assert normalize("İSTANBUL'da [İSİM] Bey, MOTOR ISINIYOR!") == "istanbul da bey motor ısınıyor"


def test_wer_and_cer() -> None:
    ref = "motor gaz verince devir yükselmiyor"
    assert wer(ref, ref) == 0.0
    assert wer(ref, "motor gaz verince devir yükseliyor") == pytest.approx(1 / 5)
    assert wer(ref, "") == 1.0
    assert wer("", "") == 0.0
    assert (
        0
        < cer(ref, "motor gaz verince devir yükseliyor")
        < wer(ref, "motor gaz verince devir yükseliyor")
    )


def test_reference_text_ignores_masked_names() -> None:
    assert wer("Ben [İSİM], Tuzla Marina'dan.", "Ben Ahmet Tuzla Marina'dan") == pytest.approx(
        1 / 4
    )


# --- Gerçek model (isteğe bağlı) ----------------------------------------------------------


@pytest.mark.skipif(os.environ.get("RUN_STT_TESTS") != "1", reason="RUN_STT_TESTS=1 değil")
async def test_real_faster_whisper_tiny_on_silence(tmp_path: Path) -> None:
    pytest.importorskip("faster_whisper")
    audio = write_wav(tmp_path / "sessiz.wav", channels=1, seconds=2.0)

    result = await FasterWhisperTranscriber("tiny").transcribe(audio)

    assert result.duration_sec == pytest.approx(2.0, abs=0.1)
    assert result.segments == []  # sessizlikte metin uydurulmamalı (VAD)


# --- Stereo sıralaması: segmentleri duraklamalardan bölme (#124) --------------------------------


def test_split_at_pauses_breaks_segment_on_long_silence() -> None:
    from types import SimpleNamespace

    from app.stt.providers import split_at_pauses

    words = [
        SimpleNamespace(start=0.0, end=0.4, word=" Merhaba"),
        SimpleNamespace(start=0.5, end=0.9, word=" buyurun."),
        # 3 sn sessizlik: arada öteki kanalda müşteri konuştu
        SimpleNamespace(start=3.9, end=4.3, word=" Teknenin"),
        SimpleNamespace(start=4.4, end=4.8, word=" adı?"),
    ]

    parts = split_at_pauses(words)

    assert [(p.start_ms, p.end_ms, p.text) for p in parts] == [
        (0, 900, "Merhaba buyurun."),
        (3900, 4800, "Teknenin adı?"),
    ]


def test_split_at_pauses_keeps_short_gaps_together() -> None:
    from types import SimpleNamespace

    from app.stt.providers import split_at_pauses

    words = [SimpleNamespace(start=i * 0.5, end=i * 0.5 + 0.4, word=f" k{i}") for i in range(4)]

    assert len(split_at_pauses(words)) == 1

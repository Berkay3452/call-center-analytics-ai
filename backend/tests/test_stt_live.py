"""Canlı transkript yayını (#323): zamana göre sıralı segment bildirimi ve Redis Stream yazımı."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.transcript_stream import TranscriptPublisher, stream_key
from app.stt.base import SttSegment, TranscriptionResult
from app.stt.pipeline import transcribe_call
from app.stt.providers import FasterWhisperTranscriber

pytestmark = pytest.mark.filterwarnings("ignore")


def ns(start: float, end: float, text: str) -> Any:
    return SimpleNamespace(start=start, end=end, text=text)


class ChannelModel:
    """Kanal başına hazır segmentler döner; her segmentin NE ZAMAN çekildiğini kaydeder."""

    def __init__(self) -> None:
        self.pulled: list[str] = []
        self.data = {
            "rep": [ns(0.0, 1.0, "Miço Usta, buyurun."), ns(3.0, 4.0, "Hangi marina?")],
            "customer": [ns(1.2, 2.8, "Motor tekliyor."), ns(4.2, 5.0, "Kalamış.")],
        }

    def transcribe(self, audio: Any, **kwargs: Any) -> Any:
        def gen() -> Any:
            for s in self.data[audio]:
                self.pulled.append(s.text)
                yield s

        return gen(), SimpleNamespace(language="tr", duration=5.0)


async def test_live_emits_segments_in_time_order_across_channels() -> None:
    model = ChannelModel()
    transcriber = FasterWhisperTranscriber(model=model)
    got: list[SttSegment] = []

    result = await transcriber.transcribe_live(
        {"rep": "rep", "customer": "customer"}, on_segment=got.append
    )

    # Kanallar ayrı çözülse de yayın gerçek konuşma sırasıyla akar.
    assert [(s.speaker, s.text) for s in got] == [
        ("rep", "Miço Usta, buyurun."),
        ("customer", "Motor tekliyor."),
        ("rep", "Hangi marina?"),
        ("customer", "Kalamış."),
    ]
    assert result.segments == got
    assert result.duration_sec == 5.0


async def test_live_pulls_channels_alternately_not_one_after_another() -> None:
    model = ChannelModel()
    transcriber = FasterWhisperTranscriber(model=model)
    seen_when_first_emitted: list[list[str]] = []

    def sink(seg: SttSegment) -> None:
        if not seen_when_first_emitted:
            seen_when_first_emitted.append(list(model.pulled))

    await transcriber.transcribe_live({"rep": "rep", "customer": "customer"}, on_segment=sink)

    # İlk segment yayınlandığında müşteri kanalı da başlamıştı, ama temsilci kanalı bitmemişti:
    # sırayla "önce tüm temsilci, sonra tüm müşteri" çözümü olsaydı "Hangi marina?" çekilirdi.
    assert "Motor tekliyor." in seen_when_first_emitted[0]
    assert "Hangi marina?" not in seen_when_first_emitted[0]


async def test_live_result_equals_non_live_result_per_channel() -> None:
    model = ChannelModel()
    transcriber = FasterWhisperTranscriber(model=model)
    live = await transcriber.transcribe_live(
        {"rep": "rep", "customer": "customer"}, on_segment=lambda s: None
    )
    rep = await transcriber.transcribe_array("rep")
    cust = await transcriber.transcribe_array("customer")

    expected = sorted(
        [s.model_copy(update={"speaker": "rep"}) for s in rep.segments]
        + [s.model_copy(update={"speaker": "customer"}) for s in cust.segments],
        key=lambda s: s.start_ms,
    )
    assert live.segments == expected


def _stereo_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.stt import pipeline
    from tests.test_stt import write_wav

    audio = write_wav(tmp_path / "c.wav", channels=2)
    monkeypatch.setattr(pipeline, "split_stereo", lambda path: ("rep", "customer"))
    return audio


async def test_pipeline_live_stereo_notifies_and_returns_same_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _stereo_setup(tmp_path, monkeypatch)
    got: list[SttSegment] = []

    result = await transcribe_call(
        audio,
        FasterWhisperTranscriber(model=ChannelModel()),
        layout="stereo_rep_left",
        on_segment=got.append,
    )
    plain = await transcribe_call(
        audio, FasterWhisperTranscriber(model=ChannelModel()), layout="stereo_rep_left"
    )

    assert [t.model_dump() for t in result.turns] == [t.model_dump() for t in plain.turns]
    assert [s.speaker for s in got] == ["rep", "customer", "rep", "customer"]


async def test_failing_sink_does_not_break_transcription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _stereo_setup(tmp_path, monkeypatch)

    def bad(_: SttSegment) -> None:
        raise RuntimeError("redis koptu")

    result = await transcribe_call(
        audio,
        FasterWhisperTranscriber(model=ChannelModel()),
        layout="stereo_rep_left",
        on_segment=bad,
    )

    assert len(result.turns) == 4


class PlainTranscriber:
    """`transcribe_live` yok (API/stub gibi): segmentler bitişte sıralı bildirilir."""

    name = "plain"

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        return TranscriptionResult(
            language="tr",
            duration_sec=3,
            model="plain",
            segments=[
                SttSegment(start_ms=2000, end_ms=3000, text="ikinci"),
                SttSegment(start_ms=0, end_ms=1000, text="birinci"),
            ],
        )


async def test_provider_without_live_support_notifies_after_finish_in_order(tmp_path: Path) -> None:
    from tests.test_stt import write_wav

    audio = write_wav(tmp_path / "m.wav", channels=1)
    got: list[SttSegment] = []

    await transcribe_call(audio, PlainTranscriber(), layout="mono", on_segment=got.append)

    assert [s.text for s in got] == ["birinci", "ikinci"]


async def test_mono_live_has_unknown_speaker(tmp_path: Path) -> None:
    from tests.test_stt import write_wav

    audio = write_wav(tmp_path / "m.wav", channels=1)
    model = ChannelModel()
    model.data[str(audio)] = [ns(0.0, 1.0, "Merhaba"), ns(1.0, 2.0, "motor")]
    got: list[SttSegment] = []

    await transcribe_call(
        audio,
        FasterWhisperTranscriber(model=model),
        layout="mono",
        on_segment=got.append,
    )

    assert [(s.speaker, s.text) for s in got] == [(None, "Merhaba"), (None, "motor")]


# --- Redis yayıncısı ------------------------------------------------------------------------


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.added: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.expired: list[tuple[str, int]] = []
        self.closed = False

    def xadd(self, key: str, fields: dict[str, Any], **kwargs: Any) -> str:
        if self.fail:
            raise ConnectionError("down")
        self.added.append((key, fields, kwargs))
        return "1-0"

    def expire(self, key: str, seconds: int) -> None:
        self.expired.append((key, seconds))

    def close(self) -> None:
        self.closed = True


def test_publisher_writes_ordered_events_with_bounds() -> None:
    redis = FakeRedis()
    pub = TranscriptPublisher(redis, "abc", maxlen=100, ttl_s=60)  # type: ignore[arg-type]

    pub.publish_segment(SttSegment(start_ms=0, end_ms=500, text=" Merhaba ", speaker="rep"))
    pub.publish_segment(SttSegment(start_ms=600, end_ms=900, text="Selam"))
    pub.publish_done()

    key = stream_key("abc")
    assert [e[0] for e in redis.added] == [key, key, key]
    assert [e[1]["type"] for e in redis.added] == ["segment", "segment", "done"]
    assert [e[1]["seq"] for e in redis.added] == [1, 2, 3]
    assert redis.added[0][1]["text"] == "Merhaba" and redis.added[0][1]["speaker"] == "rep"
    assert redis.added[1][1]["speaker"] == "unknown"
    assert redis.added[0][2] == {"maxlen": 100, "approximate": True}
    assert redis.expired[-1] == (key, 60)


def test_publisher_error_event_carries_fixed_code_only() -> None:
    redis = FakeRedis()
    pub = TranscriptPublisher(redis, "abc")  # type: ignore[arg-type]
    pub.publish_error()
    assert redis.added[0][1] == {"type": "error", "seq": 1, "code": "stt_failed"}


def test_publisher_disables_itself_after_first_redis_failure() -> None:
    redis = FakeRedis(fail=True)
    pub = TranscriptPublisher(redis, "abc")  # type: ignore[arg-type]

    pub.publish_segment(SttSegment(start_ms=0, end_ms=1, text="x"))  # hata fırlatmaz
    assert pub.enabled is False
    redis.fail = False
    pub.publish_segment(SttSegment(start_ms=0, end_ms=1, text="y"))
    assert redis.added == []  # kapandıktan sonra tekrar denenmez


def test_publisher_without_client_is_a_noop() -> None:
    pub = TranscriptPublisher(None, "abc")
    assert pub.enabled is False
    pub.publish_segment(SttSegment(start_ms=0, end_ms=1, text="x"))
    pub.publish_done()
    pub.close()

"""Çağrı sesinden konuşma turlarına (#15).

Sağlayıcı (`Transcriber`) yalnızca "ne söylendi"yi verir; burada konuşmacılar ayrılır ve ardışık
aynı konuşmacı parçaları tek tura birleştirilir. Çıktı, analiz akışının (#48, #49) beklediği
`SegmentIn` listesine doğrudan çevrilebilir.

Konuşmacı ayrımı (`STT_CHANNEL_LAYOUT`):
- `stereo_rep_left` / `stereo_rep_right`: santral kayıtları çoğunlukla iki kanallıdır; her kanal
  ayrı yazıya çevrilir, temsilcinin kanalı ayarla belirtilir. CPU'da en ucuz ve en doğru yöntem.
- `mono`: tek kanal; sağlayıcı konuşmacıyı bilmiyorsa turlar `unknown` olur. Model tabanlı ayrım
  (diarization) CPU'da yavaş olduğu için sonraki adımdır.
"""

import asyncio
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from app.agents.base import Speaker
from app.schemas.api import SegmentIn
from app.stt.base import SttError, SttSegment, Transcriber

log = structlog.get_logger(__name__)

ChannelLayout = Literal["mono", "stereo_rep_left", "stereo_rep_right"]
SAMPLE_RATE = 16_000


class SpeakerTurn(BaseModel):
    speaker: Speaker
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str


class CallTranscription(BaseModel):
    turns: list[SpeakerTurn]
    duration_sec: float
    model: str
    layout: ChannelLayout
    processing_s: float = Field(description="STT'nin harcadığı süre (hız ölçümü için).")

    def to_segments(self) -> list[SegmentIn]:
        """Analiz akışının girdisi. `unknown` konuşmacı şimdilik müşteri sayılır (#47 notu)."""
        return [
            SegmentIn(
                speaker="rep" if t.speaker == "rep" else "customer",
                text=t.text,
                start_ms=t.start_ms,
                end_ms=t.end_ms,
            )
            for t in self.turns
        ]


def merge_turns(segments: list[SttSegment], default: Speaker = "unknown") -> list[SpeakerTurn]:
    """Zamana göre sıralar; ardışık aynı konuşmacı parçalarını tek tura birleştirir."""
    turns: list[SpeakerTurn] = []
    for seg in sorted(segments, key=lambda s: (s.start_ms, s.end_ms)):
        text = seg.text.strip()
        if not text:
            continue
        speaker = seg.speaker or default
        if turns and turns[-1].speaker == speaker:
            last = turns[-1]
            turns[-1] = last.model_copy(
                update={"text": f"{last.text} {text}", "end_ms": max(last.end_ms, seg.end_ms)}
            )
        else:
            turns.append(
                SpeakerTurn(speaker=speaker, start_ms=seg.start_ms, end_ms=seg.end_ms, text=text)
            )
    return turns


def audio_channels(path: Path) -> int:
    """Ses dosyasının kanal sayısı (WAV için standart kütüphane, diğerleri için PyAV)."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path)) as wav:
                return wav.getnchannels()
        except wave.Error:
            pass  # sıkıştırılmış WAV vb.: PyAV dener
    try:
        import av
    except ImportError as exc:
        raise SttError("Ses biçimi okunamadı: `stt` ekstrasını kurun.") from exc
    try:
        container = av.open(str(path))
        try:
            channels = int(container.streams.audio[0].codec_context.channels)
        finally:
            container.close()
    except Exception as exc:
        raise SttError(f"Ses dosyası açılamadı: {exc}") from exc
    return channels


def split_stereo(path: Path) -> tuple[Any, Any]:
    """İki kanalı ayrı 16 kHz mono dizilere ayırır (faster-whisper'ın çözücüsüyle)."""
    try:
        from faster_whisper import decode_audio
    except ImportError as exc:
        raise SttError("Stereo ayrımı için `stt` ekstrası gerekir.") from exc
    try:
        left, right = decode_audio(str(path), sampling_rate=SAMPLE_RATE, split_stereo=True)
    except Exception as exc:
        raise SttError(f"Ses çözümlenemedi: {exc}") from exc
    return left, right


def write_wav(samples: Any, path: Path) -> None:
    """float32 [-1, 1] diziyi 16 bit mono WAV olarak yazar (API sağlayıcılarına göndermek için)."""
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())


async def _transcribe_channel(
    transcriber: Transcriber, samples: Any, language: str, workdir: Path, name: str
) -> list[SttSegment]:
    # Yerel model diziyi doğrudan alır; API sağlayıcıları dosya ister.
    transcribe_array = getattr(transcriber, "transcribe_array", None)
    if transcribe_array is not None:
        result = await transcribe_array(samples, language=language)
    else:
        path = workdir / f"{name}.wav"
        write_wav(samples, path)
        result = await transcriber.transcribe(path, language=language)
    return result.segments


async def transcribe_call(
    audio_path: Path,
    transcriber: Transcriber,
    *,
    layout: ChannelLayout = "mono",
    language: str = "tr",
) -> CallTranscription:
    """Çağrı sesini konuşmacı turlarına çevirir. Hata durumunda `SttError`."""
    if not await asyncio.to_thread(audio_path.exists):
        raise SttError(f"Ses dosyası yok: {audio_path.name}")
    started = time.perf_counter()

    if layout != "mono" and await asyncio.to_thread(audio_channels, audio_path) < 2:
        log.warning("stt.mono_audio_with_stereo_layout", file=audio_path.name)
        layout = "mono"

    if layout == "mono":
        result = await transcriber.transcribe(audio_path, language=language)
        turns = merge_turns(result.segments)
        duration, model = result.duration_sec, result.model
    else:
        left, right = await asyncio.to_thread(split_stereo, audio_path)
        rep, customer = (left, right) if layout == "stereo_rep_left" else (right, left)
        with tempfile.TemporaryDirectory(prefix="stt_") as tmp:
            workdir = Path(tmp)
            rep_segs = await _transcribe_channel(transcriber, rep, language, workdir, "rep")
            cust_segs = await _transcribe_channel(
                transcriber, customer, language, workdir, "customer"
            )
        segments = [s.model_copy(update={"speaker": "rep"}) for s in rep_segs] + [
            s.model_copy(update={"speaker": "customer"}) for s in cust_segs
        ]
        turns = merge_turns(segments)
        duration = max(len(left), len(right)) / SAMPLE_RATE
        model = getattr(transcriber, "name", "stt")

    processing = time.perf_counter() - started
    log.info(
        "stt.done",
        file=audio_path.name,
        layout=layout,
        turns=len(turns),
        duration_s=round(duration, 1),
        processing_s=round(processing, 1),
    )
    return CallTranscription(
        turns=turns, duration_sec=duration, model=model, layout=layout, processing_s=processing
    )

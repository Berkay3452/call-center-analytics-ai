"""STT sağlayıcıları (#15). Hepsi `Transcriber` arayüzünü uygular.

- `FasterWhisperTranscriber`: yerel Whisper (CTranslate2), CPU'da int8 ile çalışır. Ücretsiz,
  ses dışarı çıkmaz (KVKK açısından avantaj); hız model boyutuna bağlıdır. `stt` ekstrası gerekir.
- `OpenAICompatibleTranscriber`: OpenAI uyumlu Whisper API'si (ör. Groq whisper-large-v3).
  Hızlıdır, ama ses üçüncü tarafa gider ve kota vardır.
- `StubTranscriber`: ses dosyasının yanındaki `.txt` transkripti okur ("Müşteri: ..." satırları).
  STT kurulmadan zinciri (ses → analiz → ekran) denemek ve testler içindir; gerçek STT değildir.

Karşılaştırma için: `python -m scripts.stt_benchmark` (WER, hız).
"""

import asyncio
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from app.services.transcript_text import parse_transcript, with_timings
from app.stt.base import SttError, SttSegment, TranscriptionResult

log = structlog.get_logger(__name__)


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))


# --- Yerel: faster-whisper ----------------------------------------------------------------


@lru_cache(maxsize=2)
def _load_whisper(model_size: str, compute_type: str, cpu_threads: int) -> Any:
    """Modeli bir kez yükler (ilk çağrıda indirilir, ~500 MB small); süreç boyunca saklanır."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - ekstra kurulu değilse
        raise SttError(
            "faster-whisper kurulu değil: `uv sync --extra ai --extra stt` çalıştırın."
        ) from exc
    log.info("stt.model_loading", model=model_size, compute_type=compute_type)
    return WhisperModel(
        model_size, device="cpu", compute_type=compute_type, cpu_threads=cpu_threads
    )


class FasterWhisperTranscriber:
    name = "faster_whisper"

    def __init__(
        self,
        model_size: str = "small",
        *,
        compute_type: str = "int8",
        cpu_threads: int = 0,
        beam_size: int = 5,
        model: Any = None,
    ) -> None:
        self.model_size = model_size
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.beam_size = beam_size
        self._model = model  # testlerde sahte model verilebilir
        # CTranslate2 modeli aynı anda tek iş için kullanılır (CPU zaten dolu).
        self._lock = threading.Lock()

    def _get_model(self) -> Any:
        if self._model is None:
            self._model = _load_whisper(self.model_size, self.compute_type, self.cpu_threads)
        return self._model

    def _run(self, audio: Any, language: str) -> TranscriptionResult:
        with self._lock:
            model = self._get_model()
            try:
                segments, info = model.transcribe(
                    audio,
                    language=language,
                    beam_size=self.beam_size,
                    vad_filter=True,  # sessizlikleri atlar: hız ve uydurma metne karşı
                    condition_on_previous_text=False,  # uzun kayıtta tekrar döngüsünü önler
                )
                # `segments` tembel üreteçtir; asıl çözümleme burada, kilit içinde yapılır.
                out = [
                    SttSegment(start_ms=_ms(s.start), end_ms=_ms(s.end), text=s.text.strip())
                    for s in segments
                    if s.text and s.text.strip()
                ]
            except SttError:
                raise
            except Exception as exc:
                raise SttError(f"Ses çözümlenemedi: {type(exc).__name__}: {exc}") from exc
        return TranscriptionResult(
            language=getattr(info, "language", language) or language,
            duration_sec=float(getattr(info, "duration", 0.0) or 0.0),
            segments=out,
            model=f"faster-whisper/{self.model_size}/{self.compute_type}",
        )

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        return await asyncio.to_thread(self._run, str(audio_path), language)

    async def transcribe_array(self, audio: Any, *, language: str = "tr") -> TranscriptionResult:
        """Çözülmüş ses dizisi (16 kHz mono float32) için; stereo kanal ayrımında kullanılır."""
        return await asyncio.to_thread(self._run, audio, language)


# --- API: OpenAI uyumlu Whisper -----------------------------------------------------------


class OpenAICompatibleTranscriber:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str = "whisper-large-v3",
        timeout_s: float = 300.0,
        client: Any = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise SttError("STT_API_KEY tanımlı değil.")
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=self.timeout_s
            )
        return self._client

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        import openai

        client = self._get_client()
        try:
            with audio_path.open("rb") as audio:
                resp = await client.audio.transcriptions.create(
                    model=self.model,
                    file=audio,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        except (openai.APIConnectionError, openai.RateLimitError, openai.APITimeoutError) as exc:
            raise SttError(f"STT servisine ulaşılamadı: {exc}", transient=True) from exc
        except openai.APIStatusError as exc:
            raise SttError(
                f"STT servisi hata verdi ({exc.status_code}): {exc.message}",
                transient=exc.status_code >= 500,
            ) from exc

        segments = [
            SttSegment(start_ms=_ms(s.start), end_ms=_ms(s.end), text=s.text.strip())
            for s in (getattr(resp, "segments", None) or [])
            if s.text and s.text.strip()
        ]
        if not segments and getattr(resp, "text", "").strip():
            segments = [SttSegment(start_ms=0, end_ms=0, text=resp.text.strip())]
        return TranscriptionResult(
            language=getattr(resp, "language", None) or language,
            duration_sec=float(getattr(resp, "duration", 0.0) or 0.0),
            segments=segments,
            model=f"api/{self.model}",
        )


# --- Stub: yan dosyadan transkript ---------------------------------------------------------


class StubTranscriber:
    name = "stub"

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        sidecar = audio_path.with_suffix(".txt")
        if not sidecar.exists():
            raise SttError(
                f"Stub STT için {sidecar.name} bulunamadı (ses yanında 'Müşteri: ...' metni)."
            )
        timed = with_timings(parse_transcript(sidecar.read_text(encoding="utf-8")))
        segments = [
            SttSegment(start_ms=start, end_ms=end, text=seg.text, speaker=seg.speaker)
            for seg, start, end in timed
        ]
        return TranscriptionResult(
            language=language,
            duration_sec=(segments[-1].end_ms / 1000) if segments else 0.0,
            segments=segments,
            model="stub",
        )

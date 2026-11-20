"""Yalnız karşılaştırma için STT sağlayıcıları (#331). Üretimde kullanılmaz.

`HfCtcTranscriber`: Hugging Face wav2vec2/CTC modelleri (ör. Türkçe XLS-R). `torch` ve
`transformers` projenin bağımlılığı değildir; geçici eklenir:

    uv run --extra stt --with torch --with transformers python -m scripts.stt_benchmark \\
        --candidate xlsr-tr --audio <klasör>

CTC modelleri noktalama, büyük harf ve rakam üretmez; kelime zamanı çerçeveden gelir.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.stt.base import SttError, TranscriptionResult
from app.stt.duzeltme import Corrector
from app.stt.providers import _corrected, split_at_pauses

SAMPLE_RATE = 16_000


class HfCtcTranscriber:
    name = "hf_ctc"

    def __init__(
        self,
        model_id: str,
        *,
        corrector: Corrector | None = None,
        chunk_s: int = 20,
        pipe: Any = None,
    ) -> None:
        self.model_id = model_id
        self.corrector = corrector
        self.chunk_s = chunk_s
        self._pipe = pipe  # testlerde sahte boru hattı verilebilir

    def _get_pipe(self) -> Any:
        if self._pipe is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise SttError(
                    "hf_ctc için torch ve transformers gerekir: "
                    "`uv run --extra stt --with torch --with transformers ...`"
                ) from exc
            self._pipe = pipeline("automatic-speech-recognition", model=self.model_id, device=-1)
        return self._pipe

    def _run(self, audio: Any) -> TranscriptionResult:
        pipe = self._get_pipe()
        out = pipe(
            {"raw": audio, "sampling_rate": SAMPLE_RATE},
            chunk_length_s=self.chunk_s,
            stride_length_s=(4, 2),
            return_timestamps="word",
        )
        words = [
            SimpleNamespace(
                start=c["timestamp"][0] or 0.0,
                end=c["timestamp"][1] or 0.0,
                word=" " + c["text"].strip(),
            )
            for c in (out.get("chunks") or [])
            if c.get("text", "").strip()
        ]
        segments = [_corrected(s, self.corrector) for s in split_at_pauses(words)]
        return TranscriptionResult(
            language="tr",
            duration_sec=len(audio) / SAMPLE_RATE,
            segments=segments,
            model=f"hf_ctc/{self.model_id}",
        )

    async def transcribe(self, audio_path: Path, *, language: str = "tr") -> TranscriptionResult:
        try:
            from faster_whisper import decode_audio

            audio = await asyncio.to_thread(decode_audio, str(audio_path), SAMPLE_RATE)
        except Exception as exc:
            raise SttError(f"Ses çözümlenemedi: {exc}") from exc
        return await asyncio.to_thread(self._run, audio)

    async def transcribe_array(self, audio: Any, *, language: str = "tr") -> TranscriptionResult:
        return await asyncio.to_thread(self._run, audio)

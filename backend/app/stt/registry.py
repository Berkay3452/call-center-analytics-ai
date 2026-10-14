"""Ayarlara göre STT sağlayıcısını kurar (`STT_PROVIDER`)."""

from app.core.config import Settings
from app.stt.base import Transcriber
from app.stt.providers import (
    FasterWhisperTranscriber,
    OpenAICompatibleTranscriber,
    StubTranscriber,
)


def build_transcriber(settings: Settings, provider: str | None = None) -> Transcriber:
    """`provider` verilirse ayardaki yerine o kullanılır (karşılaştırma script'i için)."""
    name = provider or settings.stt_provider
    if name == "faster_whisper":
        return FasterWhisperTranscriber(
            settings.whisper_model,
            compute_type=settings.whisper_compute_type,
            cpu_threads=settings.whisper_cpu_threads,
            beam_size=settings.whisper_beam_size,
            download_root=settings.whisper_download_root,
        )
    if name == "openai_compatible":
        return OpenAICompatibleTranscriber(
            base_url=settings.stt_api_base_url,
            api_key=settings.stt_api_key.get_secret_value() if settings.stt_api_key else None,
            model=settings.stt_api_model,
            timeout_s=settings.stt_timeout_s,
        )
    if name == "stub":
        return StubTranscriber()
    raise ValueError(f"Bilinmeyen STT sağlayıcısı: {name}")

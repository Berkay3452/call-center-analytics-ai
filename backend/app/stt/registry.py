"""Ayarlara göre STT sağlayıcısını kurar (`STT_PROVIDER`)."""

import structlog

from app.core.config import Settings
from app.stt.base import Transcriber
from app.stt.duzeltme import build_corrector
from app.stt.providers import (
    FasterWhisperTranscriber,
    OpenAICompatibleTranscriber,
    StubTranscriber,
)

log = structlog.get_logger(__name__)


def build_transcriber(settings: Settings, provider: str | None = None) -> Transcriber:
    """`provider` verilirse ayardaki yerine o kullanılır (karşılaştırma script'i için)."""
    name = provider or settings.stt_provider
    if name == "openai_compatible" and not settings.stt_allow_external:
        raise ValueError(
            "Harici STT kapalı: STT_ALLOW_EXTERNAL=true verilmeden ham ses gönderilmez."
        )
    corrector = build_corrector(settings.stt_correction_enabled, settings.stt_correction_file)
    if name == "faster_whisper":
        return FasterWhisperTranscriber(
            settings.whisper_model,
            compute_type=settings.whisper_compute_type,
            cpu_threads=settings.whisper_cpu_threads,
            beam_size=settings.whisper_beam_size,
            vad_threshold=settings.whisper_vad_threshold,
            download_root=settings.whisper_download_root,
            initial_prompt=settings.whisper_initial_prompt,
            hotwords=settings.whisper_hotwords,
            corrector=corrector,
        )
    if name == "hf_ctc":  # yalnız karşılaştırma (#331): üretim sağlayıcısı değildir
        from app.stt.benchmark_providers import HfCtcTranscriber

        return HfCtcTranscriber(settings.whisper_model, corrector=corrector)
    if name == "openai_compatible":
        log.warning("stt.external_enabled", base_url=settings.stt_api_base_url)
        return OpenAICompatibleTranscriber(
            base_url=settings.stt_api_base_url,
            api_key=settings.stt_api_key.get_secret_value() if settings.stt_api_key else None,
            model=settings.stt_api_model,
            timeout_s=settings.stt_timeout_s,
            corrector=corrector,
        )
    if name == "stub":
        return StubTranscriber()
    raise ValueError(f"Bilinmeyen STT sağlayıcısı: {name}")

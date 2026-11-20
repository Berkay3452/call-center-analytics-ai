"""STT aday modelleri (#331): karşılaştırma için tek yerden tanım.

Yalnızca `scripts.stt_benchmark --candidate <ad>` ve `scripts.stt_aday_kosusu` kullanır; üretim
varsayılanı `Settings.whisper_model` / `STT_PROVIDER` ile belirlenir ve buradan etkilenmez.
Bilgiler Hugging Face model sayfalarından doğrulandı (2026-11-20, `docs/stt_karari.md`).
"""

from dataclasses import dataclass
from typing import Literal

ProviderName = Literal["faster_whisper", "hf_ctc", "openai_compatible"]


@dataclass(frozen=True)
class Candidate:
    name: str
    provider: ProviderName
    model: str  # faster-whisper: boyut ya da CT2 repo; hf_ctc: HF repo; api: model adı
    license: str
    download_gb: float
    timestamps: str  # canlı transkript (#315) için: segment/kelime zamanı desteği
    note: str
    external: bool = False  # True: ses üçüncü tarafa gider (yalnız sentetik ses, izinli)


CANDIDATES: dict[str, Candidate] = {
    c.name: c
    for c in (
        Candidate(
            "small",
            "faster_whisper",
            "small",
            "MIT",
            0.48,
            "segment + kelime",
            "Önceki varsayılan (referans).",
        ),
        Candidate(
            "medium",
            "faster_whisper",
            "medium",
            "MIT",
            1.53,
            "segment + kelime",
            "Systran/faster-whisper-medium.",
        ),
        Candidate(
            "large-v3",
            "faster_whisper",
            "large-v3",
            "MIT",
            3.09,
            "segment + kelime",
            "Systran/faster-whisper-large-v3; int8 ~2-3 GB bellek.",
        ),
        Candidate(
            "large-v3-turbo",
            "faster_whisper",
            "large-v3-turbo",
            "MIT",
            1.62,
            "segment + kelime",
            "Mevcut varsayılan (#330).",
        ),
        Candidate(
            "large-v3-tr",
            "faster_whisper",
            "oguzhangokboru/whisper-large-v3-tr",
            "Apache-2.0",
            3.09,
            "segment + kelime",
            "large-v3'ün Türkçe ince ayarı (LoRA birleştirilmiş, ~272 saat herkese açık Türkçe "
            "ses), CT2; kart ölçütleri yazarın kendi doğrulama setinden.",
        ),
        Candidate(
            "turbo-tr-itu",
            "faster_whisper",
            "RsGoksel/RsGoksel_ITU_Mainframe-ct2",
            "MIT",
            1.62,
            "segment + kelime",
            "large-v3-turbo'nun Türkçe ince ayarı, CT2; ölçütler yazarın kendi bildirimi.",
        ),
        Candidate(
            "xlsr-tr",
            "hf_ctc",
            "mpoyraz/wav2vec2-xls-r-300m-cv8-turkish",
            "Apache-2.0",
            1.26,
            "kelime (CTC çerçeve zamanı)",
            "wav2vec2 XLS-R 300M CTC, Common Voice 8 TR (kart WER %10,6, okuma sesi); noktalama, "
            "büyük harf ve rakam yok; torch + transformers gerekir.",
        ),
        Candidate(
            "groq-large-v3",
            "openai_compatible",
            "whisper-large-v3",
            "MIT (model)",
            0.0,
            "segment",
            "Ücretsiz kotalı bulut Whisper (Groq). API anahtarı gerekir; yalnız sentetik ses.",
            external=True,
        ),
    )
}

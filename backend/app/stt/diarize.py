"""Tek kanallı (mono) kayıtlarda konuşmacı ayrımı: metin tabanlı, dil modeliyle.

Mono kayıtta ses kanalı konuşmacıyı söylemez; STT çıktısı tek parça kalır. Burada yazıya
çevrilen metin cümlelere bölünür ve dil modeli her cümlenin temsilciye (Miço Usta) mı yoksa
müşteriye mi ait olduğunu soru-cevap akışına bakarak etiketler. Akustik ayrım (ses
özelliklerinden konuşmacı bulma) değildir; santral kayıtları iki kanallıysa o yöntem
kullanılır ve daha doğrudur.

Etiketleme başarısız olursa (LLM kapalı, geçersiz çıktı) çağrı bozulmaz: parçalar `unknown`
kalır ve eski davranış (tek tur) sürer.
"""

import re
from typing import Literal

import structlog
from pydantic import BaseModel

from app.assistant.llm import AssistantLLM, AssistantLLMError
from app.stt.base import SttSegment

log = structlog.get_logger(__name__)

MAX_SENTENCES = 250
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")

SYSTEM_PROMPT = """Sen bir çağrı merkezi konuşma çözümleyicisisin.
Bir telefon görüşmesinin yazıya çevrilmiş cümleleri sırayla verilecek. Görüşme, tekne bakım
ve servis firması Miço Usta'nın temsilcisi ("rep") ile arayan müşteri ("customer") arasındadır.
Her cümlenin kimin söylediğini belirle.

İpuçları:
- Temsilci firmayı karşılar ("Miço Usta, iyi günler"), tekne adını/modelini/marinayı sorar,
  usta atar, randevu ve fiyat bilgisi verir, görüşmeyi kapatır.
- Müşteri sorunu anlatır, tekne ve konum bilgisini söyler, soruları cevaplar, randevuyu kabul eder.
- Cümleler genellikle soru-cevap şeklinde dönüşümlü gider; ardışık birkaç cümle aynı kişiye ait
  olabilir.
- Emin olamadığın cümlede önceki cümlenin konuşmacısını koru.

Her cümle için bir etiket ver: cümle numarası (`n`) ve `speaker` ("rep" veya "customer")."""


class SentenceLabel(BaseModel):
    n: int
    speaker: Literal["rep", "customer"]


class SpeakerLabels(BaseModel):
    labels: list[SentenceLabel]


def split_sentences(segments: list[SttSegment]) -> list[SttSegment]:
    """Parçaları cümlelere böler; zaman damgasını karakter oranıyla paylaştırır."""
    out: list[SttSegment] = []
    for seg in segments:
        parts = [p.strip() for p in _SENTENCE.findall(seg.text) if p.strip()]
        if len(parts) <= 1:
            out.append(seg)
            continue
        total = sum(len(p) for p in parts)
        span = max(seg.end_ms - seg.start_ms, 0)
        cursor = 0
        start = seg.start_ms
        for part in parts:
            cursor += len(part)
            end = seg.start_ms + round(span * cursor / total)
            out.append(seg.model_copy(update={"text": part, "start_ms": start, "end_ms": end}))
            start = end
    return out


async def label_speakers(segments: list[SttSegment], llm: AssistantLLM) -> list[SttSegment]:
    """Cümlelere konuşmacı etiketi ekler. Başarısız olursa girdiyi değiştirmeden döner."""
    if any(s.speaker is not None for s in segments):
        return segments  # sağlayıcı konuşmacıyı zaten biliyor
    sentences = split_sentences(segments)
    if not sentences or len(sentences) > MAX_SENTENCES:
        return segments
    numbered = "\n".join(f"{i}. {s.text}" for i, s in enumerate(sentences, start=1))
    try:
        reply = await llm.ask(
            "smart",
            SYSTEM_PROMPT,
            f"## Cümleler ({len(sentences)} adet)\n{numbered}\n\n"
            f"`labels` listesinde 1'den {len(sentences)}'e her numara için bir öğe olmalı. Şemayı "
            "tekrar yazma, değerleri ver. Örnek biçim: "
            '{"labels": [{"n": 1, "speaker": "rep"}, {"n": 2, "speaker": "customer"}]}',
            SpeakerLabels,
        )
    except AssistantLLMError as exc:
        log.warning("stt.diarize_failed", error=str(exc))
        return segments
    by_number = {item.n: item.speaker for item in reply.labels}
    if len(by_number) < len(sentences) // 2:
        log.warning("stt.diarize_length_mismatch", got=len(by_number), want=len(sentences))
        return segments
    # Eksik numarayı önceki cümlenin konuşmacısıyla doldur (ilk cümle için sonrakini al).
    first = next((by_number[n] for n in sorted(by_number)), "rep")
    out: list[SttSegment] = []
    current = by_number.get(1, first)
    for number, sentence in enumerate(sentences, start=1):
        current = by_number.get(number, current)
        out.append(sentence.model_copy(update={"speaker": current}))
    return out

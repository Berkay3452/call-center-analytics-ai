"""Kullanıcıya gösterilen kısa Türkçe hata iletileri (#271).

`calls.error` arayüzde görünür. LLM/STT sağlayıcısının ham (İngilizce, iç ayrıntı içeren) hata
gövdesi ya da istisna metni oraya yazılmaz; ayrıntı yalnızca sunucu günlüğünde ve `agent_runs`
kaydındadır. Bu modül, istisna ve ajan sonuçlarından güvenli ileti üretir.
"""

from collections.abc import Iterable
from typing import Protocol

NO_SPEECH = "Seste konuşma bulunamadı."
UNEXPECTED = "Beklenmeyen bir hata oluştu; ayrıntı sunucu günlüğünde. Yeniden deneyebilirsiniz."

_KIND_TR = {
    "timeout": "süre aşımı",
    "validation": "geçersiz çıktı",
    "runtime": "servis hatası",
}


class _FailedRun(Protocol):
    agent: str
    status: str
    error_kind: str | None


def analysis_error(runs: Iterable[_FailedRun]) -> str:
    """Başarısız ajanları ve hata türünü (ham ileti olmadan) özetler."""
    parts = [
        f"{r.agent}: {_KIND_TR.get(r.error_kind or '', 'hata')}"
        for r in runs
        if r.status == "failed"
    ]
    detail = "; ".join(parts) or "analiz tamamlanamadı"
    return f"Analiz başarısız ({detail}). Ayrıntı ajan kayıtlarında."


def stt_error(message: str, *, transient: bool) -> str:
    """STT hatası: kendi ürettiğimiz ileti korunur, sağlayıcı ayrıntısı atılır."""
    if message == NO_SPEECH:
        return f"Yazıya çevirme başarısız: {NO_SPEECH}"
    if transient:
        return "Yazıya çevirme başarısız: servise şu an ulaşılamadı; biraz sonra yeniden deneyin."
    return "Yazıya çevirme başarısız: ses dosyası işlenemedi veya servis hata verdi."

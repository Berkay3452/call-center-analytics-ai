"""LLM istemci fabrikası.

Ücretsiz API sağlayıcılarının hepsi OpenAI-uyumlu uç sunduğu için tek istemci (ChatOpenAI)
farklı `base_url` ile kullanılır. İki katman vardır:
- fast  : duygu, anahtar kelime, triage gibi hafif işler
- smart : özet, şikayet tespiti, RAG yanıtı gibi zor işler

LangChain bağımlılığı `ai` ekstrasındadır ve tembel import edilir; API bu paket olmadan da açılır.
"""

import asyncio
from typing import TYPE_CHECKING, Literal
from weakref import WeakKeyDictionary

from app.core.config import Settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

Tier = Literal["fast", "smart"]

# Sağlayıcıların OpenAI-uyumlu varsayılan adresleri (LLM_BASE_URL ile ezilebilir).
PROVIDER_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "ollama": "http://localhost:11434/v1",
}


class LLMNotConfiguredError(RuntimeError):
    pass


def _resolve_base_url(settings: Settings) -> str:
    if settings.llm_base_url:
        return settings.llm_base_url
    try:
        return PROVIDER_BASE_URLS[settings.llm_provider]
    except KeyError as exc:
        raise LLMNotConfiguredError(
            "LLM_PROVIDER=openai_compatible için LLM_BASE_URL verilmelidir."
        ) from exc


def get_chat_model(tier: Tier, settings: Settings, *, temperature: float = 0.0) -> "BaseChatModel":
    """İstenen katman için yapılandırılmış sohbet modelini döndürür."""
    model = settings.llm_fast_model if tier == "fast" else settings.llm_smart_model
    if not model:
        raise LLMNotConfiguredError(f"LLM_{tier.upper()}_MODEL tanımlı değil (.env).")
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    if not api_key and settings.llm_provider != "ollama":
        raise LLMNotConfiguredError("LLM_API_KEY tanımlı değil (.env).")

    from langchain_openai import ChatOpenAI  # tembel import (ai ekstrası)

    return ChatOpenAI(
        model=model,
        base_url=_resolve_base_url(settings),
        api_key=api_key or "ollama",  # Ollama anahtar istemez ama alan zorunlu
        temperature=temperature,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


# Her event loop için ayrı semafor: Celery görevleri her seferinde yeni döngü açar
# (asyncio.run) ve bir döngüye bağlı semafor başka döngüde kullanılamaz.
_semaphores: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = WeakKeyDictionary()


def llm_semaphore(settings: Settings) -> asyncio.Semaphore:
    """Eşzamanlı LLM çağrısını sınırlar (ücretsiz katmanların oran sınırına karşı).

    Kullanım: `async with llm_semaphore(settings): await model.ainvoke(...)`
    """
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(settings.llm_max_concurrency)
        _semaphores[loop] = sem
    return sem

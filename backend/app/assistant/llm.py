"""Asistanın LLM çağrısı: tek yerde mesaj kurma, eşzamanlılık sınırı, JSON ayıklama ve doğrulama.

Çağrı analizindeki agent'larla (`app/agents/llm_agent.py`) aynı altyapıyı kullanır: ayarlardaki
sağlayıcı/model, eşzamanlılık sınırı ve JSON ayıklama.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from app.agents.llm_agent import extract_json_object, format_validation_error
from app.core.config import Settings, get_settings
from app.llm.client import (
    LLMNotConfiguredError,
    get_chat_model,
    is_transient_llm_error,
    llm_semaphore,
)

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

log = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)


class AssistantLLMError(RuntimeError):
    """LLM çağrısı başarısız oldu veya geçerli çıktı alınamadı (API bunu 503'e çevirir)."""


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


class AssistantLLM:
    """Şemaya uyan JSON üreten LLM çağrısı. Testlerde `model` olarak sahte model verilir."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model: "BaseChatModel | None" = None,
        fallback_model: "BaseChatModel | None" = None,
    ) -> None:
        self._settings = settings
        self._model = model
        self._fallback_model = fallback_model  # testlerde sahte yedek model

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def _fallback_for(
        self, tier: Literal["fast", "smart"], primary: str | None, exc: BaseException
    ) -> "BaseChatModel | None":
        """Geçici hatada kullanılacak yedek model (yoksa None); sahte birincil modelde açılmaz."""
        if not is_transient_llm_error(exc):
            return None
        if self._fallback_model is not None:
            return self._fallback_model
        if self._model is not None:
            return None
        name = self.settings.llm_fallback_for("assistant", tier, primary)
        if name is None:
            return None
        try:
            return get_chat_model(tier, self.settings, model=name)
        except LLMNotConfiguredError:
            return None

    async def ask(
        self,
        tier: Literal["fast", "smart"],
        system: str,
        user: str,
        schema: type[T],
        *,
        max_fix_attempts: int = 1,
    ) -> T:
        """JSON ister; şemaya uymazsa hata mesajıyla en fazla `max_fix_attempts` kez düzeltir."""
        from langchain_core.messages import HumanMessage, SystemMessage

        model = self._model or get_chat_model(tier, self.settings)
        primary_name = getattr(model, "model_name", None)
        fallback_used = False
        schema_json = schema.model_json_schema()
        prompt = (
            f"{user}\n\n## Çıktı biçimi\n"
            f"Yalnızca bu JSON şemasına uyan TEK bir JSON nesnesi döndür:\n{schema_json}"
        )
        feedback = ""
        for attempt in range(max_fix_attempts + 1):
            content = prompt + (f"\n\n## Düzeltme gerekli\n{feedback}" if feedback else "")
            messages = [SystemMessage(system), HumanMessage(content)]
            try:
                async with llm_semaphore(self.settings):
                    response = await model.ainvoke(messages)
            except Exception as exc:  # sağlayıcı, ağ, kota
                log.warning("assistant.llm_error", error=str(exc)[:200])
                fallback = None if fallback_used else self._fallback_for(tier, primary_name, exc)
                if fallback is None:
                    raise AssistantLLMError(f"LLM çağrısı başarısız: {type(exc).__name__}") from exc
                # Geçici hata: bir kez yedek modelle denenir; düzeltme turları da onunla sürer.
                log.warning("assistant.fallback", reason=type(exc).__name__)
                model, fallback_used = fallback, True
                try:
                    async with llm_semaphore(self.settings):
                        response = await model.ainvoke(messages)
                except Exception as exc2:
                    log.warning("assistant.fallback_failed", error=str(exc2)[:200])
                    raise AssistantLLMError(
                        f"LLM çağrısı başarısız (yedek model de): {type(exc2).__name__}"
                    ) from exc2
            text = response.content if isinstance(response.content, str) else str(response.content)
            try:
                return schema.model_validate(extract_json_object(text))
            except ValidationError as exc:
                feedback = format_validation_error(exc)
            except ValueError as exc:
                feedback = str(exc)
            log.warning("assistant.invalid_output", attempt=attempt + 1, error=feedback[:200])
        raise AssistantLLMError(f"LLM geçerli çıktı üretemedi: {feedback[:200]}")

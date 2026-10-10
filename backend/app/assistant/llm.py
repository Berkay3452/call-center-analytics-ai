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
from app.llm.client import get_chat_model, llm_semaphore

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
    ) -> None:
        self._settings = settings
        self._model = model

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

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
        schema_json = schema.model_json_schema()
        prompt = (
            f"{user}\n\n## Çıktı biçimi\n"
            f"Yalnızca bu JSON şemasına uyan TEK bir JSON nesnesi döndür:\n{schema_json}"
        )
        feedback = ""
        for attempt in range(max_fix_attempts + 1):
            content = prompt + (f"\n\n## Düzeltme gerekli\n{feedback}" if feedback else "")
            try:
                async with llm_semaphore(self.settings):
                    response = await model.ainvoke([SystemMessage(system), HumanMessage(content)])
            except Exception as exc:  # sağlayıcı, ağ, kota
                log.warning("assistant.llm_error", error=str(exc)[:200])
                raise AssistantLLMError(f"LLM çağrısı başarısız: {type(exc).__name__}") from exc
            text = response.content if isinstance(response.content, str) else str(response.content)
            try:
                return schema.model_validate(extract_json_object(text))
            except ValidationError as exc:
                feedback = format_validation_error(exc)
            except ValueError as exc:
                feedback = str(exc)
            log.warning("assistant.invalid_output", attempt=attempt + 1, error=feedback[:200])
        raise AssistantLLMError(f"LLM geçerli çıktı üretemedi: {feedback[:200]}")

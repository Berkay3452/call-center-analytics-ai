"""Testler için sahte sohbet modeli: gerçek LLM'e gitmeden agent'ları dener."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """Sırayla verilen cevapları döner ve kendisine gönderilen mesajları kaydeder.

    Cevap bir `Exception` ise çağrıda o istisna fırlatılır (sağlayıcı hatası benzetimi).
    """

    responses: list[str | Exception]
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    model_name: str = "sahte-model"

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("ScriptedChatModel: beklenenden fazla çağrı yapıldı.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        message = AIMessage(
            content=response,
            usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def last_system(self) -> str:
        return str(self.calls[-1][0].content)

    @property
    def last_user(self) -> str:
        return str(self.calls[-1][-1].content)


def scripted(*responses: str | Exception) -> ScriptedChatModel:
    return ScriptedChatModel(responses=list(responses), calls=[])

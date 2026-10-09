"""LLM ile çalışan analiz agent'larının ortak tabanı.

Her agent yalnızca dört şey tanımlar: adı, prompt dosyası, çıktı şeması ve model katmanı.
Mesajları kurma, LLM'i çağırma, JSON'u ayıklama, şemayla doğrulama ve hatayı `AgentResult`'a
çevirme burada tek yerde yapılır.

Yapılandırılmış çıktı neden prompt ile isteniyor: ücretsiz sağlayıcıların (Groq, Gemini,
OpenRouter, Ollama) hepsi aynı "structured output" özelliğini desteklemiyor. Şemayı prompt'a
yazıp dönen JSON'u Pydantic ile doğrulamak hepsinde çalışır; şemaya uymayan çıktı
`error_kind="validation"` ile döner ve orkestratör hata mesajını geri verip bir kez daha dener.
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import structlog
from pydantic import BaseModel, ValidationError

from app.agents.base import AgentResult, AnalysisContext, BaseAgent, Segment
from app.core.config import Settings, get_settings
from app.llm.client import LLMNotConfiguredError, get_chat_model, llm_semaphore

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage

log = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

SPEAKER_LABELS = {"rep": "Firma", "customer": "Müşteri", "unknown": "Bilinmiyor"}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class OutputParseError(ValueError):
    """LLM cevabından geçerli bir JSON nesnesi çıkarılamadı."""


@cache
def load_prompt(name: str) -> str:
    """`prompts/<name>.md` dosyasını okur (süreç boyunca önbellekte tutulur)."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def extract_json_object(text: str) -> dict[str, Any]:
    """LLM cevabından tek bir JSON nesnesi çıkarır.

    Modeller bazen JSON'u ```json bloğuna sarar veya önüne/arkasına açıklama ekler; ilk `{` ile
    son `}` arası alınır.
    """
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise OutputParseError("Cevapta JSON nesnesi bulunamadı.")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OutputParseError(f"JSON okunamadı: {exc.msg} (konum {exc.pos}).") from exc
    if not isinstance(data, dict):
        raise OutputParseError("Cevap bir JSON nesnesi olmalı.")
    return data


def format_validation_error(exc: ValidationError) -> str:
    """Pydantic hatasını LLM'e geri verilebilecek kısa, okunur bir metne çevirir."""
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(nesnenin tamamı)"
        lines.append(f"- {loc}: {err['msg']}")
    return "Çıktı şemaya uymuyor:\n" + "\n".join(lines)


def format_transcript(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.idx}] {SPEAKER_LABELS[s.speaker]}: {s.text_masked}" for s in segments)


def _message_text(content: str | list[Any]) -> str:
    if isinstance(content, str):
        return content
    parts = [p if isinstance(p, str) else str(p.get("text", "")) for p in content]
    return "".join(parts)


class LLMAgent[T: BaseModel](BaseAgent[T]):
    """LLM çağıran agent'ların tabanı.

    Alt sınıflar `name`, `prompt_version`, `output_schema`, `model_tier` ve `prompt_file`
    tanımlar. Gerekirse `postprocess` ile çıktıya alana özgü kontrol ekler.

    Testlerde `model` parametresiyle sahte bir sohbet modeli verilir; verilmezse ayarlardaki
    sağlayıcı ve model (`.env`) çalışma anında kullanılır.
    """

    prompt_file: ClassVar[str]

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

    # --- Alt sınıfların değiştirebileceği adımlar ------------------------------------------

    def postprocess(self, output: T, ctx: AnalysisContext) -> T:
        """Şema doğrulamasından sonra alana özgü kontrol. `ValueError` → doğrulama hatası."""
        return output

    def build_messages(self, ctx: AnalysisContext) -> "list[BaseMessage]":
        from langchain_core.messages import HumanMessage, SystemMessage

        system = f"{load_prompt('common')}\n\n{load_prompt(self.prompt_file)}"
        return [SystemMessage(system), HumanMessage(self._user_message(ctx))]

    def _user_message(self, ctx: AnalysisContext) -> str:
        parts = [
            "## Görüşme metni (kişisel veriler maskelenmiştir)",
            format_transcript(ctx.segments) or "(boş görüşme)",
        ]
        if ctx.call_info is not None:
            info = ctx.call_info.model_dump(mode="json", exclude_none=True)
            if info:
                parts += ["## Çağrı bilgisi", json.dumps(info, ensure_ascii=False)]
        if ctx.prior:
            parts += [
                "## Önceki agent'ların çıktıları",
                json.dumps(ctx.prior, ensure_ascii=False, indent=2),
            ]
        if ctx.feedback:
            parts += [
                "## Düzeltme gerekli",
                "Önceki cevabın geçersizdi. Aynı hatayı yapmadan cevabı yeniden üret.",
                ctx.feedback,
            ]
        schema = json.dumps(self.output_schema.model_json_schema(), ensure_ascii=False)
        parts += [
            "## Çıktı biçimi",
            "Yalnızca aşağıdaki JSON şemasına uyan TEK bir JSON nesnesi döndür. "
            "Açıklama, markdown veya ek metin yazma.",
            schema,
        ]
        return "\n\n".join(parts)

    # --- Çalıştırma ------------------------------------------------------------------------

    def _resolve_model(self) -> tuple["BaseChatModel", str | None]:
        if self._model is not None:
            return self._model, getattr(self._model, "model_name", None)
        settings = self.settings
        name = settings.llm_model_for(self.name, self.model_tier)
        return get_chat_model(self.model_tier, settings, model=name), name

    def _fail(self, error: str, kind: str, **extra: Any) -> AgentResult[T]:
        return AgentResult[T].model_validate(
            {
                "agent": self.name,
                "status": "failed",
                "error": error,
                "error_kind": kind,
                "prompt_version": self.prompt_version,
                **extra,
            }
        )

    async def run(self, ctx: AnalysisContext) -> AgentResult[T]:
        try:
            model, model_name = self._resolve_model()
        except LLMNotConfiguredError as exc:
            return self._fail(f"LLM yapılandırılmadı: {exc}", "runtime")

        try:
            async with llm_semaphore(self.settings):
                response = await model.ainvoke(self.build_messages(ctx))
        except Exception as exc:  # sağlayıcı, ağ, kota vb.; orkestratör tekrar denemez
            log.warning("agent.llm_error", agent=self.name, error=str(exc))
            return self._fail(f"LLM çağrısı başarısız: {type(exc).__name__}: {exc}", "runtime")

        usage = getattr(response, "usage_metadata", None) or {}
        meta = {
            "model": model_name,
            "tokens_in": usage.get("input_tokens", 0),
            "tokens_out": usage.get("output_tokens", 0),
        }
        try:
            data = extract_json_object(_message_text(response.content))
            output = cast(T, self.output_schema.model_validate(data))
            output = self.postprocess(output, ctx)
        except OutputParseError as exc:
            return self._fail(str(exc), "validation", **meta)
        except ValidationError as exc:
            return self._fail(format_validation_error(exc), "validation", **meta)
        except ValueError as exc:  # postprocess kontrolleri
            return self._fail(f"Çıktı kontrolü: {exc}", "validation", **meta)

        return AgentResult[T].model_validate(
            {
                "agent": self.name,
                "status": "ok",
                "output": output,
                "prompt_version": self.prompt_version,
                **meta,
            }
        )

"""Uçlar arasında ortak kullanılan şemalar."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Tüm hata yanıtlarının biçimi (bkz. app/core/errors.py)."""

    error: ErrorBody


class Page[T](BaseModel):
    """Sayfalı liste yanıtı."""

    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


ComponentState = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    env: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, ComponentState]

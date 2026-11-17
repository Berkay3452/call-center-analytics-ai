"""Uygulama hataları ve tek tip hata yanıtı.

Tüm hatalar şu gövdeyle döner (frontend tek bir biçimi işler):
    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import REQUEST_ID_HEADER

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Tüm uygulama hatalarının tabanı. Servis katmanı HTTP bilmeden bu hataları fırlatır."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.headers = headers or {}  # yanıt başlıkları (ör. Retry-After)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"


class TooManyRequestsError(AppError):
    """Hız sınırı aşıldı (#271). `Retry-After` saniye cinsinden başlıkta ve ayrıntıdadır."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_s: int) -> None:
        retry_after = max(1, int(retry_after_s))
        super().__init__(
            message,
            details={"retry_after_s": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


def error_json(
    request_id: str | None,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Tek tip hata gövdesi; ara katmanlar (hız sınırı, gövde sınırı) de bunu kullanır."""
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }
    out = dict(headers or {})
    if status_code == 401:
        out["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=status_code, content=body, headers=out or None)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return error_json(
        getattr(request.state, "request_id", None), status_code, code, message, details, headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            request, exc.status_code, exc.code, exc.message, exc.details, exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "İstek doğrulanamadı.",
            # `ctx` (ör. model doğrulayıcının ValueError'u) JSON'a çevrilemez; yalnızca
            # alan yolu, mesaj ve tür gönderilir.
            {"errors": [{k: e[k] for k in ("loc", "msg", "type")} for e in exc.errors()]},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Beklenmeyen hata: ayrıntı loga yazılır, istemciye iç bilgi sızdırılmaz. Bu işleyici
        # RequestContextMiddleware'in DIŞINDA çalışır (Starlette ServerErrorMiddleware): bağlam
        # değişkenleri temizlenmiş olur, bu yüzden istek kimliği günlüğe ve yanıta elle eklenir.
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_error",
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            error_type=type(exc).__name__,
        )
        response = _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            # Ekran görüntüsünden günlükte aranabilsin diye kimlik mesajın içinde de görünür.
            f"Beklenmeyen hata. (Hata kodu: {request_id})" if request_id else "Beklenmeyen hata.",
        )
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response

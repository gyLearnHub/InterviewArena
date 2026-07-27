from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INVALID_UPLOAD_TYPE = "INVALID_UPLOAD_TYPE"
    RESUME_PARSE_FAILED = "RESUME_PARSE_FAILED"
    LLM_API_KEY_MISSING = "LLM_API_KEY_MISSING"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    TOO_MANY_REQUESTS = "TOO_MANY_REQUESTS"
    BUSINESS_ERROR = "BUSINESS_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "请求参数不正确。",
    ErrorCode.UNAUTHORIZED: "请先登录。",
    ErrorCode.FORBIDDEN: "没有权限访问该资源。",
    ErrorCode.NOT_FOUND: "资源不存在。",
    ErrorCode.CONFLICT: "资源已存在。",
    ErrorCode.INVALID_UPLOAD_TYPE: "上传格式不支持，需要重新上传哦。",
    ErrorCode.RESUME_PARSE_FAILED: "简历解析失败，请重新上传。",
    ErrorCode.LLM_API_KEY_MISSING: "需要配置好API Key噢。",
    ErrorCode.NETWORK_TIMEOUT: "当前网络环境不好，请稍后重试。",
    ErrorCode.TOO_MANY_REQUESTS: "请求过于频繁，请稍后再试。",
    ErrorCode.BUSINESS_ERROR: "业务处理失败。",
    ErrorCode.INTERNAL_ERROR: "服务器开小差了，请稍后重试。",
}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        message: str | None = None,
        details: Any | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.message = message or ERROR_MESSAGES[code]
        self.details = details

    def __str__(self) -> str:
        base = f"{self.code.value}: {self.message}"
        if self.details is None:
            return base
        return f"{base} details={self.details}"


def safe_error_code(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.code.value
    return exc.__class__.__name__


def build_error_response(error: AppError) -> dict[str, dict[str, Any]]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=build_error_response(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        app_error = AppError(
            ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT,
            details=exc.errors(),
        )
        return JSONResponse(
            status_code=app_error.status_code,
            content=build_error_response(app_error),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        app_error = AppError(
            ErrorCode.INTERNAL_ERROR,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        request_id = getattr(request.state, "request_id", None)
        headers = {"X-Request-ID": request_id} if request_id else None
        return JSONResponse(
            status_code=app_error.status_code,
            content=build_error_response(app_error),
            headers=headers,
        )

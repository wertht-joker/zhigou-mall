"""业务异常与全局异常处理器

约定：业务代码只管抛 AppError 的子类（如 NotFoundError / ConflictError），
由这里统一转成「真实 HTTP 状态码 + {code, message, data, trace_id}」响应。
路由层因此不再需要散落的 try/except。

trace_id：优先取请求中间件写入的 request.state.trace_id（P2 阶段由
RequestContextMiddleware 注入），未注入时临时生成，保证错误响应可追溯。
"""
import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.error")


class AppError(Exception):
    """业务异常基类：status_code 决定 HTTP 状态码，code 为响应体编码"""

    status_code: int = 500
    code: int = 500
    default_message: str = "服务器内部错误"

    def __init__(self, message: str | None = None, *, data: Any = None):
        self.message = message or self.default_message
        self.data = data
        super().__init__(self.message)


class BadRequestError(AppError):
    """请求参数/内容不合法"""

    status_code = 400
    code = 400
    default_message = "请求参数有误"


class AuthError(AppError):
    """未登录或凭证失效"""

    status_code = 401
    code = 401
    default_message = "未登录或登录已过期"


class ForbiddenError(AppError):
    """已登录但权限不足"""

    status_code = 403
    code = 403
    default_message = "无权访问"


class NotFoundError(AppError):
    """资源不存在"""

    status_code = 404
    code = 404
    default_message = "资源不存在"


class ConflictError(AppError):
    """资源冲突（如用户名已存在）"""

    status_code = 409
    code = 409
    default_message = "资源冲突"


class AppServiceError(AppError):
    """服务内部处理失败"""

    status_code = 500
    code = 500
    default_message = "服务处理失败"


class RateLimitError(AppError):
    """触发限流"""

    status_code = 429
    code = 429
    default_message = "请求过于频繁，请稍后再试"


class ServiceUnavailableError(AppError):
    """依赖不可用（健康检查未通过）"""

    status_code = 503
    code = 503
    default_message = "服务暂不可用"


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or uuid.uuid4().hex


def _payload(code: int, message: str, trace_id: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data, "trace_id": trace_id}


def register_exception_handlers(app: FastAPI) -> None:
    """把各类异常统一映射为 {code, message, data, trace_id}"""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        payload = _payload(exc.code, exc.message, _trace_id(request), exc.data)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        payload = _payload(exc.status_code, str(exc.detail), _trace_id(request))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(part) for part in first.get("loc", []))
        message = f"参数校验失败：{loc} {first.get('msg', '')}".strip()
        payload = _payload(400, message, _trace_id(request))
        return JSONResponse(status_code=400, content=payload)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id(request)
        logger.exception("未处理异常 trace_id=%s path=%s", trace_id, request.url.path)
        payload = _payload(500, "服务器内部错误", trace_id)
        return JSONResponse(status_code=500, content=payload)

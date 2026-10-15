"""请求上下文中间件：trace_id 生成/透传 + 访问日志

用纯 ASGI 中间件实现（而非 BaseHTTPMiddleware），避免包装层影响 SSE 流式输出。
每个请求都会：
1. 从 X-Request-ID 请求头读取上游 trace_id，没有则新生成一个；
2. 写入 scope["state"]，供全局异常处理器与业务日志使用；
3. 在响应头回写 X-Request-ID，方便前端/网关串联链路；
4. 输出一条带耗时与状态码的访问日志。
"""
import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.access")

TRACE_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        trace_id = request.headers.get(TRACE_HEADER) or uuid.uuid4().hex
        scope.setdefault("state", {})
        scope["state"]["trace_id"] = trace_id

        status_code = 0
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[TRACE_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            cost_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "%s %s -> %s (%sms)",
                request.method,
                request.url.path,
                status_code,
                cost_ms,
                extra={"trace_id": trace_id},
            )

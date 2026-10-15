"""结构化日志

- JSON 行格式（log_json=True）便于日志采集系统解析；False 时输出可读文本
- 每条日志自动带上 trace_id（由请求中间件写入），便于按请求追踪
"""
import json
import logging
import sys
from typing import Any

from app.core.config import settings

# trace_id 以 LogRecord 附加字段的形式传入：logger.info(..., extra={"trace_id": tid})
TRACE_FIELD = "trace_id"


class JsonFormatter(logging.Formatter):
    """把日志渲染成单行 JSON"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = getattr(record, TRACE_FIELD, None)
        if trace_id:
            payload[TRACE_FIELD] = trace_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """可读文本格式，本地开发更友好"""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, TRACE_FIELD, None)
        prefix = f"[{record.levelname}]"
        if trace_id:
            prefix += f"[{trace_id[:8]}]"
        base = f"{self.formatTime(record, '%H:%M:%S')} {prefix} {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging() -> None:
    """初始化根 logger：统一格式、级别，并把 uvicorn 的日志也收编"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_json else PlainFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # 让 uvicorn 的日志走同一套格式化（不再自带 handler）
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

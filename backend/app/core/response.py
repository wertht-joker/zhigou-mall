"""统一响应结构：{code, message, data}

约定：
- 成功：HTTP 200 + code 200 + data
- 失败：由全局异常处理器统一产出（见 core/errors.py），
  路由层无需自己拼错误结构，只调用 success() 组装成功响应。
"""
from typing import Any

from pydantic import BaseModel

SUCCESS_CODE = 200


class ApiResponse(BaseModel):
    """统一响应体（同时用于接口文档展示）"""

    code: int = SUCCESS_CODE
    message: str = "ok"
    data: Any = None


def success(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应"""
    return ApiResponse(code=SUCCESS_CODE, message=message, data=data).model_dump()


def fail(code: int, message: str, data: Any = None) -> dict:
    """构造失败响应（一般只由全局异常处理器调用）"""
    return ApiResponse(code=code, message=message, data=data).model_dump()

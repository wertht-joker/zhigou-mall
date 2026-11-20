"""售后 Agent 接口请求模型"""
from pydantic import BaseModel, Field


class ConfirmActionRequest(BaseModel):
    """确认执行：必须带发起提案时的会话 ID（令牌与会话绑定）"""

    session_id: int
    # 可选幂等键：客户端重试时复用同一个值
    idempotency_key: str | None = Field(default=None, max_length=64)


class CancelActionRequest(BaseModel):
    """取消提案：只改提案状态，不触碰业务数据"""

    session_id: int

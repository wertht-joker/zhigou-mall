"""问答相关请求/响应模型"""
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """提问请求"""
    question: str
    # 会话ID，传入则续接多轮对话；不传则新建会话
    session_id: int | None = None


class Source(BaseModel):
    """引用来源"""
    doc_id: int
    doc_name: str
    chunk_index: int
    text: str
    score: float
    # 可信回答守卫：该引用是否真的支撑了答案（supported/partial/unsupported/unused）
    verdict: str | None = None
    # 支撑强度（0-1，词面覆盖代理分数）
    confidence: float | None = None
    # 时效政策版本：前端展示“v2 · 2026-11-01 生效”
    version: int | None = None
    policy_key: str | None = None
    effective_from: datetime | None = None


class ChatResponse(BaseModel):
    """问答响应：答案 + 引用来源 + 会话/消息ID + 可信回答校验汇总"""
    answer: str
    sources: list[Source]
    session_id: int
    message_id: int
    # 充分性门控 + claim 级校验结果（faithfulness / claims / sources / message）
    verification: dict | None = None

"""文档相关请求/响应模型"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentUpdateRequest(BaseModel):
    """编辑文档元数据（政策标识与版本号不可改，保证历史版本可追溯）"""
    name: str = Field(min_length=1, max_length=255)
    category_id: int | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class KnowledgeGapDraftRequest(BaseModel):
    """根据一组缺口问题生成 FAQ 草稿（按商家隔离）"""
    queries: list[str] = Field(min_length=1, max_length=10)
    tenant_id: int | None = None


class KnowledgeGapPublishRequest(BaseModel):
    """把 FAQ 草稿发布为知识库文档，并关闭对应商家的缺口"""
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    queries: list[str] = Field(default_factory=list, max_length=10)
    category_id: int | None = None
    tenant_id: int | None = None


class DocumentOut(BaseModel):
    """文档响应模型"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    tenant_id: int | None = None
    size: int
    chunk_count: int
    status: str
    category_id: int | None
    # 时效政策版本（普通文档为 None / 1 / active）
    policy_key: str | None = None
    version: int = 1
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    supersedes_id: int | None = None
    lifecycle_status: str = "active"
    created_at: datetime

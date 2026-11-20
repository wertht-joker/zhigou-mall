"""文档元数据模型"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Document(Base):
    """知识文档元数据（向量数据单独存 Milvus）"""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_tenant_created", "tenant_id", "created_at"),
        # 时效政策检索：按政策标识 + 版本、按生效时间过滤
        Index("ix_documents_policy", "tenant_id", "policy_key", "version"),
        Index("ix_documents_effective", "tenant_id", "effective_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属租户（多租户隔离边界）
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 原始文件名
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 文件格式：pdf / docx / xlsx / md
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 文件大小（字节）
    size: Mapped[int] = mapped_column(Integer, default=0)
    # 切分后的块数量
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # 所属分类ID（可空）
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 状态：processing 处理中 / done 已完成 / failed 失败
    status: Mapped[str] = mapped_column(String(20), default="processing")
    # ===== 时效政策版本（方向 C）=====
    # 同一份政策的稳定标识，例如 return_policy；为空表示普通知识文档
    policy_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 政策版本号（从 1 开始递增）
    version: Mapped[int] = mapped_column(Integer, default=1)
    # 生效区间：为空表示不限制；检索时按业务时间过滤
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 被哪个版本取代（保留历史版本，不物理删除）
    supersedes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # active 当前版本 / superseded 已被新版本取代
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="active")
    # 上传时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

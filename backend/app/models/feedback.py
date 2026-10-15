"""回答反馈模型"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Feedback(Base):
    """对 AI 回答的反馈（点赞/点踩）"""

    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_tenant_message", "tenant_id", "message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属租户（多租户隔离边界）
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 类型：up 有用 / down 无用
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

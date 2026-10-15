"""用户模型（登录鉴权）"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class User(Base):
    """系统用户"""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_tenant_username", "tenant_id", "username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属租户（多租户隔离边界）
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    # 角色：admin 管理员 / editor 编辑 / viewer 只读（user 为历史角色，等同 viewer）
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

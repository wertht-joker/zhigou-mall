"""租户模型（多租户隔离的顶层实体）

每个租户是一份独立的数据空间（企业 / 部门 / 客户）。业务表通过 tenant_id
关联到租户，查询一律按 tenant_id 过滤，实现「数据互不可见」。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Tenant(Base):
    """租户：数据的隔离边界"""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 租户编码，登录/注册时用于定位租户，全局唯一
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 状态：active 启用 / disabled 停用
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

"""租户服务：定位/创建租户

多租户的关键入口：
- 注册/登录时通过租户编码定位租户（未提供则用默认租户，兼容单租户历史数据）
- 首次访问时确保默认租户存在，让历史库平滑迁移
"""
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository

# 默认租户：历史数据与「未指定租户」的请求都归到这里
DEFAULT_TENANT_CODE = "default"
DEFAULT_TENANT_NAME = "默认租户"


def get(db: Session, tenant_id: int) -> Tenant | None:
    return TenantRepository(db).get(tenant_id)


def get_by_code(db: Session, code: str) -> Tenant | None:
    return TenantRepository(db).get_by_code(code)


def list_tenants(db: Session) -> list[Tenant]:
    return TenantRepository(db).list()


def ensure_default_tenant(db: Session) -> Tenant:
    """确保默认租户存在（幂等）"""
    repo = TenantRepository(db)
    tenant = repo.get_by_code(DEFAULT_TENANT_CODE)
    if tenant is None:
        tenant = repo.create(DEFAULT_TENANT_CODE, DEFAULT_TENANT_NAME)
    return tenant


def resolve_tenant(db: Session, code: str | None = None) -> Tenant | None:
    """按编码定位租户；未提供编码时返回默认租户"""
    if not code:
        return ensure_default_tenant(db)
    return TenantRepository(db).get_by_code(code)

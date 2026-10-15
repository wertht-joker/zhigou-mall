"""租户仓储

注意：tenants 是「租户本身」的根表，它不自带 tenant_id，因此这里不适用
tenant 过滤（scoped/apply_tenant 对未定义该列的模型自动 no-op）。
其余业务仓储一律强制按 tenant_id 过滤。
"""
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, tenant_id: int) -> Tenant | None:
        return self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def get_by_code(self, code: str) -> Tenant | None:
        return self.db.query(Tenant).filter(Tenant.code == code).first()

    def list(self) -> list[Tenant]:
        return self.db.query(Tenant).order_by(Tenant.id).all()

    def create(self, code: str, name: str, status: str = "active") -> Tenant:
        tenant = Tenant(code=code, name=name, status=status)
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant

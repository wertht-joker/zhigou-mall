"""租户接口（需 tenant:manage 权限，默认 admin）

演示多租户：管理员可查看系统内的租户列表。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.user import User
from app.schemas.user import TenantOut
from app.services import tenant_service

router = APIRouter(tags=["租户"])


@router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("tenant:manage")),
):
    """租户列表"""
    tenants = tenant_service.list_tenants(db)
    return success([TenantOut.model_validate(t).model_dump() for t in tenants])

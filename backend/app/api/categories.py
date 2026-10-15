"""分类接口（需 category:manage 权限，按租户隔离）"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryOut
from app.services import category_service

router = APIRouter(tags=["知识分类"])


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("category:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    categories = category_service.list_categories(db, tenant.id)
    return success([CategoryOut.model_validate(c).model_dump() for c in categories])


@router.post("/categories")
def create_category(
    req: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("category:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    category = category_service.create_category(db, req.name, req.parent_id, req.sort, tenant.id)
    return success(CategoryOut.model_validate(category).model_dump(), message="创建成功")


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    req: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("category:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    category = category_service.update_category(
        db, category_id, req.name, req.parent_id, req.sort, tenant.id
    )
    return success(CategoryOut.model_validate(category).model_dump(), message="更新成功")


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("category:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    category_service.delete_category(db, category_id, tenant.id)
    return success(message="删除成功")

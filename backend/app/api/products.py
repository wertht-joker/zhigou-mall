"""商品接口：前台公开浏览 + 商家管理（需 product:manage 权限）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.product import ProductSaveRequest
from app.services import product_service

router = APIRouter(tags=["商品"])


# ===== 前台（公开） =====

@router.get("/products")
def list_products(
    keyword: str | None = Query(default=None, max_length=50),
    category_id: int | None = None,
    db: Session = Depends(get_db),
):
    """商品列表（公开：全平台在售商品，按销量排序）"""
    products = product_service.list_products(db, keyword, category_id)
    return success([product_service.serialize_public(p, db) for p in products])


@router.get("/product-categories")
def list_categories(db: Session = Depends(get_db)):
    """商品分类列表（公开，平台级）"""
    return success([c.__dict__ for c in product_service.list_categories(db)])


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    """商品详情（公开）"""
    return success(product_service.serialize_public(
        product_service.get_product(db, product_id), db
    ))


# ===== 商家后台 =====

@router.get("/merchant/products")
def list_merchant_products(
    keyword: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("product:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """本店商品列表（含下架，强制商家隔离）"""
    products = product_service.list_merchant_products(db, keyword, tenant.id)
    return success([p.__dict__ for p in products])


@router.post("/merchant/products")
def create_product(
    req: ProductSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("product:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家上新"""
    product = product_service.create_product(
        db, req.model_dump(), tenant.id
    )
    return success(product.__dict__, message="商品已创建")


@router.put("/merchant/products/{product_id}")
def update_product(
    product_id: int,
    req: ProductSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("product:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家修改商品（价格/库存/上下架等）"""
    product = product_service.update_product(
        db, product_id, req.model_dump(), tenant.id
    )
    return success(product.__dict__, message="商品已更新")


@router.delete("/merchant/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("product:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家删除商品"""
    product_service.delete_product(db, product_id, tenant.id)
    return success(None, message="商品已删除")

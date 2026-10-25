"""评价接口：公开查看 + 顾客评价 + 商家回复"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.review import MerchantReplyRequest, ReviewCreateRequest
from app.services import review_service

router = APIRouter(tags=["评价"])


@router.get("/products/{product_id}/reviews")
def list_product_reviews(
    product_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """商品评价列表 + 统计（公开）"""
    return success(review_service.list_product_reviews(db, product_id, page, page_size))


@router.get("/reviews/my/reviewable")
def my_reviewable(
    product_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的「可评价」订单明细（已完成订单中未评价的商品）"""
    return success(review_service.my_reviewable(db, user.id, product_id))


@router.post("/reviews")
def create_review(
    req: ReviewCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """发表评价（凭本人已完成订单明细，一单一件一次）"""
    review = review_service.create_review(
        db, user.id, req.order_item_id, req.rating, req.content
    )
    return success(review, message="评价成功")


@router.get("/merchant/reviews")
def list_merchant_reviews(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("product:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家评价列表（仅本店商品）"""
    return success(review_service.list_merchant_reviews(db, tenant.id, page, page_size))


@router.post("/merchant/reviews/{review_id}/reply")
def reply_review(
    review_id: int,
    req: MerchantReplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("product:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家回复评价（仅本店商品的评价）"""
    review = review_service.reply_review(db, review_id, req.reply, tenant.id)
    return success(review, message="回复成功")

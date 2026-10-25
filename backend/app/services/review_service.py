"""评价服务：创建校验（本人已完成订单明细 + 一单一评）、列表统计、商家回复"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.order import Order, OrderItem
from app.models.review import Review
from app.repositories.review_repository import ReviewRepository, list_reviewable_items

ORDER_STATUS_DONE = "已完成"


def mask_username(username: str) -> str:
    """京东式昵称打码：保留首尾字符，中间打码（防骚扰，保留可读性）"""
    if not username:
        return "匿名用户"
    if len(username) <= 2:
        return username[0] + "**"
    return username[0] + "**" + username[-1]


def _serialize(db: Session, review: Review, with_product: bool = False) -> dict:
    from app.models.user import User
    from app.repositories.product_repository import ProductRepository

    user = db.query(User).filter(User.id == review.user_id).first()
    data = {
        "id": review.id,
        "product_id": review.product_id,
        "user_id": review.user_id,
        "rating": review.rating,
        "content": review.content,
        "reply": review.reply,
        "replied_at": review.replied_at,
        "created_at": review.created_at,
        "username": mask_username(user.username if user else ""),
        "product_name": "",
    }
    if with_product and review.product_id:
        product = ProductRepository(db).get(review.product_id)
        data["product_name"] = product.name if product else "（商品已删除）"
    return data


def list_product_reviews(db: Session, product_id: int, page: int = 1,
                         page_size: int = 10) -> dict:
    """商品评价列表 + 统计（公开）"""
    repo = ReviewRepository(db)
    offset = max(page - 1, 0) * page_size
    reviews = repo.list_by_product(product_id, offset=offset, limit=page_size)
    return {
        "stats": repo.stats_by_product(product_id),
        "total": repo.count_by_product(product_id),
        "items": [_serialize(db, r, with_product=True) for r in reviews],
    }


def create_review(db: Session, user_id: int, order_item_id: int,
                  rating: int, content: str) -> dict:
    """凭订单明细评价：明细必须属于本人已完成订单，且未评价过"""
    row = (
        db.query(OrderItem, Order)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(OrderItem.id == order_item_id)
        .first()
    )
    if not row:
        raise NotFoundError("订单明细不存在")
    item, order = row
    # 越权防护：不是本人的明细一律按不存在处理
    if order.user_id != user_id:
        raise NotFoundError("订单明细不存在")
    if order.status != ORDER_STATUS_DONE:
        raise BadRequestError("确认收货后才能评价")
    if not (content and content.strip()):
        raise BadRequestError("评价内容不能为空")

    repo = ReviewRepository(db)
    if repo.get_by_order_item(order_item_id):
        raise ConflictError("该商品已评价过，一单一件只能评价一次")

    review = repo.add(
        user_id=user_id,
        product_id=item.product_id,
        merchant_id=item.merchant_id,
        order_id=order.id,
        order_item_id=item.id,
        rating=rating,
        content=content.strip(),
    )
    return _serialize(db, review)


def reply_review(db: Session, review_id: int, reply: str,
                 tenant_id: int | None) -> dict:
    """商家回复评价：只能回复本店商品的评价"""
    repo = ReviewRepository(db)
    review = repo.get(review_id)
    if not review:
        raise NotFoundError("评价不存在")
    if tenant_id is not None and review.merchant_id != tenant_id:
        # 跨商家回复按不存在处理，不泄露资源
        raise NotFoundError("评价不存在")
    if review.reply:
        raise ConflictError("该评价已回复过")
    review.reply = reply.strip()
    review.replied_at = datetime.now()
    review = repo.save(review)
    return _serialize(db, review, with_product=True)


def list_merchant_reviews(db: Session, tenant_id: int | None,
                          page: int = 1, page_size: int = 20) -> dict:
    """商家评价列表（含商品名，供后台回复用）"""
    repo = ReviewRepository(db)
    offset = max(page - 1, 0) * page_size
    reviews = repo.list_by_merchant(tenant_id, offset=offset, limit=page_size)
    return {
        "total": repo.count_by_merchant(tenant_id),
        "items": [_serialize(db, r, with_product=True) for r in reviews],
    }


def my_reviewable(db: Session, user_id: int,
                  product_id: int | None = None) -> list[dict]:
    return list_reviewable_items(db, user_id, product_id)

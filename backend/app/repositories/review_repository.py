"""评价仓储"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import OrderItem
from app.models.review import Review
from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, review_id: int) -> Review | None:
        return self.db.query(Review).filter(Review.id == review_id).first()

    def get_by_order_item(self, order_item_id: int) -> Review | None:
        return (
            self.db.query(Review).filter(Review.order_item_id == order_item_id).first()
        )

    def list_by_product(self, product_id: int, offset: int = 0,
                        limit: int = 10) -> list[Review]:
        return (
            self.db.query(Review)
            .filter(Review.product_id == product_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_by_product(self, product_id: int) -> int:
        return (
            self.db.query(func.count(Review.id))
            .filter(Review.product_id == product_id)
            .scalar() or 0
        )

    def stats_by_product(self, product_id: int) -> dict:
        """单商品评价统计：平均分 + 总数 + 各星级数量"""
        rows = (
            self.db.query(Review.rating, func.count(Review.id))
            .filter(Review.product_id == product_id)
            .group_by(Review.rating)
            .all()
        )
        per_star = {star: 0 for star in range(1, 6)}
        for rating, count in rows:
            per_star[int(rating)] = count
        total = sum(per_star.values())
        weighted = sum(star * count for star, count in per_star.items())
        return {
            "total": total,
            "avg_rating": round(weighted / total, 1) if total else 0.0,
            "per_star": per_star,
            "positive_rate": (
                round((per_star[4] + per_star[5]) / total * 100) if total else 100
            ),
        }

    def add(self, **fields) -> Review:
        review = Review(**fields)
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def save(self, review: Review) -> Review:
        self.db.commit()
        self.db.refresh(review)
        return review

    def list_by_merchant(self, merchant_id: int | None = None,
                         offset: int = 0, limit: int = 50) -> list[Review]:
        """商家评价列表：按商品归属商家圈定"""
        query = self.db.query(Review)
        if merchant_id is not None:
            query = query.filter(Review.merchant_id == merchant_id)
        return (
            query.order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_by_merchant(self, merchant_id: int | None = None) -> int:
        query = self.db.query(func.count(Review.id))
        if merchant_id is not None:
            query = query.filter(Review.merchant_id == merchant_id)
        return query.scalar() or 0


def list_reviewable_items(db: Session, user_id: int,
                          product_id: int | None = None) -> list[dict]:
    """顾客「可评价」的订单明细：本人已完成订单中的商品，且尚未评价过

    联表 reviews 判断是否已评价；product_id 可选过滤（商品详情页用）。
    """
    from app.models.order import Order

    query = (
        db.query(OrderItem, Order.order_no, Order.status)
        .join(Order, Order.id == OrderItem.order_id)
        .outerjoin(Review, Review.order_item_id == OrderItem.id)
        .filter(Order.user_id == user_id, Order.status == "已完成")
        .filter(Review.id.is_(None))
    )
    if product_id is not None:
        query = query.filter(OrderItem.product_id == product_id)
    rows = query.order_by(OrderItem.id.desc()).all()
    return [
        {
            "order_item_id": item.id,
            "order_id": item.order_id,
            "order_no": order_no,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "image": item.image,
            "price": item.price,
            "quantity": item.quantity,
        }
        for item, order_no, _status in rows
    ]

"""优惠券服务：领取 / 我的券 / 下单抵扣 / 取消退回（营销域）

档位与双11活动横幅一致：满 199 减 30、满 399 减 80、满 699 减 150，
每档每用户限领一张（coupon_repository.find_by_tier 判重）。

【券生命周期】
    领取(unused) ──下单核销 redeem──▶ used（绑定 order_id）
                        ▲                    │
                        └───── 取消订单退回 ──┘
  一张表同时承担「券模板 + 用户券」：档位固定三种，配置在 COUPON_TIERS 常量，
  没有拆成「模板表 + 用户券表」——当前规模不需要，简单优先（先做对，再做优雅）。

【金额安全】抵扣取 min(面额, 订单总额)，应付最低 0 元、绝不为负；
  门槛/归属/状态校验都在服务端 redeem()，前端的选券只是入口（前端数据不可信）。

【并发处理】
  1) 领取仍是"先查后插"（check-then-act），两个并发请求可能都通过判重各领一张
     → 生产：DB 加唯一约束 UNIQUE(user_id, threshold)，捕获冲突返回"已领取"；
  2) 核销已改为条件更新（见 redeem）：
     UPDATE coupons SET status='used' WHERE id=? AND status='unused'
     影响行数 = 1 才算成功，并发两单用同一张券时只有一单能核销；
  3) redeem 成功但建单失败会让券卡在 used → 下单整体包进一个 DB 事务，
     或定时对账回扫「used 且无 order_id」的券做补偿。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.models.coupon import COUPON_UNUSED, COUPON_USED, Coupon
from app.repositories.coupon_repository import CouponRepository

# (门槛, 抵扣) 档位配置
COUPON_TIERS: list[tuple[float, float]] = [(199, 30), (399, 80), (699, 150)]
COUPON_TITLE = "双11狂欢满减券"


def _serialize(coupon: Coupon) -> dict:
    return {
        "id": coupon.id,
        "title": coupon.title,
        "threshold": coupon.threshold,
        "discount": coupon.discount,
        "status": coupon.status,
        "order_id": coupon.order_id,
        "claimed_at": coupon.claimed_at.isoformat() if coupon.claimed_at else None,
        "used_at": coupon.used_at.isoformat() if coupon.used_at else None,
    }


def list_tiers() -> list[dict]:
    """活动券档位（横幅/领券页展示用）"""
    return [{"threshold": t, "discount": d} for t, d in COUPON_TIERS]


def list_my(db: Session, user_id: int) -> list[dict]:
    return [_serialize(c) for c in CouponRepository(db).list_by_user(user_id)]


def claim(db: Session, user_id: int, threshold: float) -> dict:
    """领取指定档位券（每档限领一张）

    ⚠ find_by_tier 判重是"先查后插"，并发下有重复领取窗口——
    生产方案见模块注释【已知并发缺陷】第 1 条（唯一约束兜底）。
    """
    tier = next((t for t in COUPON_TIERS if t[0] == threshold), None)
    if not tier:
        raise NotFoundError("优惠券档位不存在")
    if CouponRepository(db).find_by_tier(user_id, threshold):
        raise BadRequestError("该档位优惠券已领取过啦")
    coupon = CouponRepository(db).create(
        user_id=user_id,
        title=COUPON_TITLE,
        threshold=tier[0],
        discount=tier[1],
        status=COUPON_UNUSED,
    )
    return _serialize(coupon)


def usable_for(db: Session, user_id: int, subtotal: float) -> list[dict]:
    """结算页可选的券：未使用且门槛 <= 当前金额"""
    return [
        _serialize(c) for c in CouponRepository(db).list_usable(user_id, subtotal)
    ]


def redeem(db: Session, user_id: int, coupon_id: int, subtotal: float) -> tuple[float, Coupon]:
    """下单核销：校验归属/状态/门槛，返回抵扣金额并绑定订单由调用方回填

    抵扣不超过订单金额（最低支付 0 元）。
    核销用条件更新（WHERE status='unused'）抢占，并发下只有一单能成功。
    """
    coupon = CouponRepository(db).get(coupon_id)
    if not coupon or coupon.user_id != user_id:
        raise NotFoundError("优惠券不存在")
    if coupon.status != COUPON_UNUSED:
        raise BadRequestError("优惠券已被使用")
    if subtotal < coupon.threshold:
        raise BadRequestError(f"该券满 {coupon.threshold:g} 元可用，还差 {coupon.threshold - subtotal:g} 元")
    discount = min(coupon.discount, subtotal)

    # 条件更新：状态仍为 unused 才能置为 used；rowcount=0 说明被并发请求抢先
    rows = (
        db.query(Coupon)
        .filter(
            Coupon.id == coupon_id,
            Coupon.user_id == user_id,
            Coupon.status == COUPON_UNUSED,
        )
        .update(
            {Coupon.status: COUPON_USED, Coupon.used_at: datetime.now()},
            synchronize_session=False,
        )
    )
    db.commit()
    if rows != 1:
        raise BadRequestError("优惠券已被使用")
    db.refresh(coupon)
    return round(discount, 2), coupon


def release_if_any(db: Session, order_id: int) -> None:
    """取消订单时退回本单核销的优惠券（重新变为未使用）

    通过 order_id 反查被本单核销的券——这就是 redeem 后要 bind_order 的原因：
    没有这个关联，取消时就不知道该退哪张券。
    条件更新保证重复取消/补偿重放不会把券的状态来回改。
    """
    db.query(Coupon).filter(
        Coupon.order_id == order_id,
        Coupon.status == COUPON_USED,
    ).update(
        {
            Coupon.status: COUPON_UNUSED,
            Coupon.order_id: None,
            Coupon.used_at: None,
        },
        synchronize_session=False,
    )
    db.commit()


def bind_order(db: Session, coupon: Coupon, order_id: int) -> None:
    """核销后绑定订单号（取消时据此退回）"""
    coupon.order_id = order_id
    CouponRepository(db).save(coupon)

"""优惠券模型"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    threshold: float
    discount: float
    status: str
    order_id: int | None = None
    claimed_at: datetime | None = None
    used_at: datetime | None = None


class CouponClaimRequest(BaseModel):
    """领券：传门槛金额定位档位（199/399/699）"""
    threshold: float

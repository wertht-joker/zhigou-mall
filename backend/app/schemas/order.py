"""订单相关模型"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = None
    variant_id: int | None = None
    variant_spec: str = ""
    product_name: str
    image: str = "📦"
    price: float
    quantity: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    total_amount: float
    status: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    logistics: str
    payment_method: str = ""
    paid_at: datetime | None = None
    # 明细由服务层填充（不在 ORM 关系里，靠 model_dump 后附加）
    items: list[OrderItemOut] = []


class BuyNowItem(BaseModel):
    """立即购买：绕过购物车，直接按商品/规格/数量下单"""
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(default=1, ge=1, le=99)


class OrderCreateRequest(BaseModel):
    """下单：购物车勾选 或 立即购买（二选一）+ 可选优惠券"""
    cart_item_ids: list[int] = Field(default_factory=list)
    buy_now: BuyNowItem | None = None
    address_id: int
    coupon_id: int | None = None


class MerchantShipRequest(BaseModel):
    """发货：新版填写物流公司 + 运单号；logistics 保留兼容旧客户端"""
    logistics: str | None = Field(default=None, max_length=100)
    logistics_company: str = Field(default="", max_length=50)
    tracking_no: str = Field(default="", max_length=50)


class LogisticsEventCreateRequest(BaseModel):
    """商家更新物流状态：只能向前推进，例如 运输中 → 派送中"""
    status: str = Field(min_length=1, max_length=20)
    description: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=100)

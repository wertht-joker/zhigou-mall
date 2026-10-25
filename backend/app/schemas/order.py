"""订单相关模型"""
from pydantic import BaseModel, ConfigDict, Field


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = None
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
    # 明细由服务层填充（不在 ORM 关系里，靠 model_dump 后附加）
    items: list[OrderItemOut] = []


class OrderCreateRequest(BaseModel):
    """下单：勾选的购物车条目（不传默认全选）+ 可选优惠券"""
    cart_item_ids: list[int] = Field(default_factory=list)
    address_id: int
    coupon_id: int | None = None


class MerchantShipRequest(BaseModel):
    logistics: str = Field(min_length=1, max_length=100)

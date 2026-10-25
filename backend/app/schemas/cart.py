"""购物车相关模型"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductOut


class CartItemOut(BaseModel):
    """购物车条目（联带商品快照）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    product: ProductOut | None = None


class CartAddRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class CartUpdateRequest(BaseModel):
    quantity: int = Field(ge=1)

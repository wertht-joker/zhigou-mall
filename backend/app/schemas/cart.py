"""购物车相关模型"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductOut, ProductVariantOut


class CartItemOut(BaseModel):
    """购物车条目（联带商品快照与所选规格）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    variant_id: int | None = None
    quantity: int
    unit_price: float = 0.0
    stock: int = 0
    variant: ProductVariantOut | None = None
    product: ProductOut | None = None


class CartAddRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)
    # 有规格的商品必须指定规格
    variant_id: int | None = None


class CartUpdateRequest(BaseModel):
    quantity: int = Field(ge=1)

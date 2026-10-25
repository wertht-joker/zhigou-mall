"""商品相关模型"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int | None = None
    category_id: int | None = None
    name: str
    subtitle: str = ""
    description: str = ""
    price: float
    original_price: float | None = None
    stock: int
    sales: int
    image: str = "📦"
    status: str = "on_sale"
    created_at: datetime


class ProductSaveRequest(BaseModel):
    """商家创建/更新商品"""
    name: str = Field(min_length=1, max_length=100)
    subtitle: str = Field(default="", max_length=200)
    description: str = ""
    price: float = Field(gt=0)
    original_price: float | None = None
    stock: int = Field(default=0, ge=0)
    image: str = Field(default="📦", max_length=20)
    category_id: int | None = None
    status: str = Field(default="on_sale", pattern="^(on_sale|off_sale)$")


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon: str
    sort: int

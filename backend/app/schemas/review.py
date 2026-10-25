"""评价相关模型"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreateRequest(BaseModel):
    """创建评价：锚定一条本人已完成订单的明细"""
    order_item_id: int
    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=500)


class MerchantReplyRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=300)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    user_id: int
    rating: int
    content: str
    reply: str | None = None
    replied_at: datetime | None = None
    created_at: datetime
    # 以下由服务层填充
    username: str = ""
    product_name: str = ""


class ReviewStats(BaseModel):
    total: int
    avg_rating: float
    per_star: dict[int, int]
    positive_rate: int

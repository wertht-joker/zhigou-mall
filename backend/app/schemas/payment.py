"""支付相关模型"""
from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    """发起支付：选择支付方式"""
    method: str = Field(default="alipay", pattern="^(alipay|wechat|unionpay)$")

"""收货地址相关模型"""
from pydantic import BaseModel, ConfigDict, Field


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receiver: str
    phone: str
    region: str
    detail: str
    is_default: bool


class AddressSaveRequest(BaseModel):
    receiver: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=5, max_length=20)
    region: str = Field(default="", max_length=100)
    detail: str = Field(min_length=1, max_length=200)
    is_default: bool = False

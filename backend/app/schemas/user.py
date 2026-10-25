"""用户认证相关模型"""
from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str
    password: str
    # 注册类型：customer 顾客（默认）/ merchant 商家入驻
    register_type: str = Field(default="customer", pattern="^(customer|merchant)$")
    # 商家入驻时的店铺名称（register_type=merchant 时必填）
    merchant_name: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str
    # 租户编码，留空则自动按用户名定位所属租户（用户名平台级唯一）
    tenant_code: str | None = None


class TenantOut(BaseModel):
    """租户（商家）响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    status: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    tenant_id: int | None = None


class TokenResponse(BaseModel):
    token: str
    user: UserOut
    tenant: TenantOut

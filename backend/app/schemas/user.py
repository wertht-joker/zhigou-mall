"""用户认证相关模型"""
from pydantic import BaseModel, ConfigDict


class RegisterRequest(BaseModel):
    username: str
    password: str
    # 租户编码，留空则使用默认租户
    tenant_code: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str
    # 租户编码，留空则使用默认租户
    tenant_code: str | None = None


class TenantOut(BaseModel):
    """租户响应"""
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

"""注册 / 登录接口

- 顾客注册：归属平台默认租户，逛商城、下单、与 AI 客服对话
- 商家入驻：创建商家（租户）+ 店铺管理员账号
- 登录：用户名平台级唯一，无需记忆租户编码即可自动定位
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import AuthError, BadRequestError
from app.core.response import success
from app.models.database import get_db
from app.schemas.user import (
    LoginRequest,
    RegisterRequest,
    TenantOut,
    TokenResponse,
    UserOut,
)
from app.services import auth_service
from app.utils import security

router = APIRouter(tags=["认证"])


@router.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册：register_type=customer 顾客注册 / merchant 商家入驻"""
    if req.register_type == "merchant":
        user, tenant = auth_service.register_merchant(
            db, req.username, req.password, req.merchant_name or ""
        )
    else:
        from app.services import tenant_service
        tenant = tenant_service.ensure_default_tenant(db)
        user = auth_service.register_customer(db, req.username, req.password, tenant.id)
    data = TokenResponse(
        token=security.create_token(user.id, user.role, tenant.id),
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    ).model_dump()
    return success(data, message="注册成功")


@router.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """登录，返回 JWT + 用户 + 商家信息（无需传租户编码，自动按用户名定位）"""
    user, tenant = auth_service.login(db, req.username, req.password, req.tenant_code)
    if tenant is None:
        raise AuthError("账号异常：未归属任何商家")
    token = security.create_token(user.id, user.role, tenant.id)
    data = TokenResponse(
        token=token,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    ).model_dump()
    return success(data, message="登录成功")

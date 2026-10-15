"""注册/登录接口（多租户）

按请求里的租户编码定位租户（留空则用默认租户），注册/登录都限定在该租户内，
登录返回里带上租户信息，供前端展示当前数据空间。
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
from app.services import auth_service, tenant_service
from app.utils import security

router = APIRouter(tags=["认证"])


@router.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册（普通用户，归属请求指定的租户）"""
    tenant = tenant_service.resolve_tenant(db, req.tenant_code)
    if tenant is None:
        raise BadRequestError("租户不存在")
    user = auth_service.register(db, req.username, req.password, tenant.id)
    return success(UserOut.model_validate(user).model_dump(), message="注册成功")


@router.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """登录，返回 JWT + 用户 + 租户信息"""
    tenant = tenant_service.resolve_tenant(db, req.tenant_code)
    if tenant is None:
        raise AuthError("租户不存在或已停用")
    user = auth_service.login(db, req.username, req.password, tenant.id)
    token = security.create_token(user.id, user.role, tenant.id)
    data = TokenResponse(
        token=token,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    ).model_dump()
    return success(data, message="登录成功")

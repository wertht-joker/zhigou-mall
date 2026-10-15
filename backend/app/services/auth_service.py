"""认证服务：注册与登录

把认证逻辑从路由搬进服务层，失败时抛 AppError 子类，
由全局异常处理器统一转成 HTTP 状态码 + 统一响应。
"""
from sqlalchemy.orm import Session

from app.core.errors import AuthError, BadRequestError, ConflictError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils import security


def register(db: Session, username: str, password: str, tenant_id: int | None = None) -> User:
    """注册普通用户"""
    if not username or not password:
        raise BadRequestError("用户名和密码不能为空")
    repo = UserRepository(db)
    if repo.get_by_username(username, tenant_id):
        raise ConflictError("用户名已存在")
    return repo.create(
        username=username,
        password_hash=security.hash_password(password),
        role="user",
        tenant_id=tenant_id,
    )


def login(db: Session, username: str, password: str, tenant_id: int | None = None) -> User:
    """校验账号密码，成功返回用户"""
    repo = UserRepository(db)
    user = repo.get_by_username(username, tenant_id)
    if not user or not security.verify_password(password, user.password_hash):
        raise AuthError("用户名或密码错误")
    return user

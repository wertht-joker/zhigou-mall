"""会话接口（需登录，按租户隔离）"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user
from app.core.errors import NotFoundError
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.session import MessageOut, SessionOut
from app.services import session_service

router = APIRouter(tags=["会话"])


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """会话列表（仅当前租户）"""
    sessions = session_service.list_sessions(db, tenant.id)
    return success([SessionOut.model_validate(s).model_dump() for s in sessions])


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """某会话的消息历史（校验会话归属当前租户）"""
    if not session_service.get_session(db, session_id, tenant.id):
        raise NotFoundError("会话不存在")
    msgs = session_service.get_history(db, session_id, limit=100)
    return success([MessageOut.model_validate(m).model_dump() for m in msgs])


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """删除会话（仅当前租户）"""
    session_service.delete_session(db, session_id, tenant.id)
    return success(message="删除成功")

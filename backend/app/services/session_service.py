"""会话管理服务：创建会话、保存消息、读取历史

对外仍暴露函数式 API（签名稳定），内部委托给 SessionRepository 做数据访问。
"""
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.session import Message, Session as SessionModel
from app.repositories.session_repository import SessionRepository


def create_session(db: Session, title: str = "新对话", tenant_id: int | None = None) -> SessionModel:
    """新建会话"""
    return SessionRepository(db).create_session(title, tenant_id)


def get_session(db: Session, session_id: int, tenant_id: int | None = None) -> SessionModel | None:
    return SessionRepository(db).get_session(session_id, tenant_id)


def save_message(
    db: Session, session_id: int, role: str, content: str, tenant_id: int | None = None
) -> Message:
    """保存一条消息"""
    return SessionRepository(db).add_message(session_id, role, content, tenant_id)


def get_history(db: Session, session_id: int, limit: int = 6) -> list[Message]:
    """读取最近 N 条消息（按时间正序返回，便于拼接上下文）"""
    return SessionRepository(db).get_history(session_id, limit)


def list_sessions(db: Session, tenant_id: int | None = None) -> list[SessionModel]:
    """会话列表（按时间倒序）"""
    return SessionRepository(db).list_sessions(tenant_id)


def delete_session(db: Session, session_id: int, tenant_id: int | None = None) -> None:
    """删除会话及其所有消息"""
    repo = SessionRepository(db)
    session = repo.get_session(session_id, tenant_id)
    if not session:
        raise NotFoundError("会话不存在")
    repo.delete_session(session)

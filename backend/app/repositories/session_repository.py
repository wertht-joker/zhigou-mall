"""会话与消息仓储"""
from sqlalchemy.orm import Session

from app.models.session import Message, Session as SessionModel
from app.repositories.base import BaseRepository, apply_tenant, scoped


class SessionRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def create_session(self, title: str = "新对话", tenant_id: int | None = None) -> SessionModel:
        session = SessionModel(title=title or "新对话")
        apply_tenant(session, tenant_id)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int, tenant_id: int | None = None) -> SessionModel | None:
        query = scoped(
            self.db.query(SessionModel).filter(SessionModel.id == session_id),
            SessionModel,
            tenant_id,
        )
        return query.first()

    def list_sessions(self, tenant_id: int | None = None) -> list[SessionModel]:
        query = scoped(self.db.query(SessionModel), SessionModel, tenant_id)
        return query.order_by(SessionModel.created_at.desc()).all()

    def add_message(
        self, session_id: int, role: str, content: str, tenant_id: int | None = None
    ) -> Message:
        message = Message(session_id=session_id, role=role, content=content)
        apply_tenant(message, tenant_id)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_history(self, session_id: int, limit: int = 6) -> list[Message]:
        """读取最近 N 条消息（按时间正序返回，便于拼接上下文）"""
        messages = (
            self.db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(messages))

    def delete_session(self, session: SessionModel) -> None:
        """删除会话及其全部消息"""
        self.db.query(Message).filter(Message.session_id == session.id).delete()
        self.db.delete(session)
        self.db.commit()

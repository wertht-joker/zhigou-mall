"""回答反馈仓储"""
from sqlalchemy.orm import Session

from app.models.feedback import Feedback
from app.repositories.base import BaseRepository, apply_tenant, scoped


class FeedbackRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def add(self, message_id: int, feedback_type: str,
            tenant_id: int | None = None) -> Feedback:
        feedback = Feedback(message_id=message_id, type=feedback_type)
        apply_tenant(feedback, tenant_id)
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def count_by_type(self, feedback_type: str, tenant_id: int | None = None) -> int:
        query = self.db.query(Feedback).filter(Feedback.type == feedback_type)
        return scoped(query, Feedback, tenant_id).count()

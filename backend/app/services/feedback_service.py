"""反馈服务（按租户隔离）"""
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.models.feedback import Feedback
from app.repositories.feedback_repository import FeedbackRepository

VALID_TYPES = ("up", "down")


def add_feedback(db: Session, message_id: int, feedback_type: str,
                 tenant_id: int | None = None) -> Feedback:
    """添加反馈（up 有用 / down 无用）"""
    if feedback_type not in VALID_TYPES:
        raise BadRequestError("反馈类型只能是 up 或 down")
    return FeedbackRepository(db).add(message_id, feedback_type, tenant_id)


def stats(db: Session, tenant_id: int | None = None) -> dict:
    """反馈统计（仅当前租户）"""
    repo = FeedbackRepository(db)
    up = repo.count_by_type("up", tenant_id)
    down = repo.count_by_type("down", tenant_id)
    return {"up": up, "down": down, "total": up + down}

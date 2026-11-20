"""AI 问答事件服务：把每轮回答转成可分析的知识缺口数据

写入失败不能影响客服主流程，因此这里统一吞掉异常并记录日志。
"""
import logging

from sqlalchemy.orm import Session

from app.models.qa_event import QaEvent
from app.repositories.qa_event_repository import QaEventRepository

logger = logging.getLogger(__name__)


def record(db: Session, *, tenant_id: int | None, user_id: int | None,
           session_id: int | None, message_id: int | None,
           query: str, answer: str, sources: list[dict] | None,
           verification: dict | None, trace: dict | None) -> QaEvent | None:
    """记录一轮问答；任何字段缺失都按“无信号”处理"""
    try:
        verification = verification or {}
        trace = trace or {}
        sufficiency = verification.get("sufficiency") or {}
        route = trace.get("route") or {}
        return QaEventRepository(db).add(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            query=(query or "").strip()[:1000],
            answer=answer or "",
            sources_count=len(sources or []),
            sufficiency=sufficiency.get("level"),
            faithfulness=verification.get("faithfulness"),
            route=route.get("strategy"),
            feedback=None,
            handled=False,
        )
    except Exception:
        logger.warning("记录 AI 问答事件失败（不影响对话）", exc_info=True)
        db.rollback()
        return None


def set_feedback(db: Session, message_id: int, feedback: str,
                 tenant_id: int | None = None) -> None:
    """点赞/点踩回填到对应问答事件"""
    try:
        QaEventRepository(db).mark_feedback(message_id, feedback, tenant_id)
    except Exception:
        logger.warning("回填问答事件反馈失败（不影响反馈提交）", exc_info=True)
        db.rollback()

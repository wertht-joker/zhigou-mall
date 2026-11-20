"""AI 问答事件仓储"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.qa_event import QaEvent
from app.repositories.base import BaseRepository, scoped


class QaEventRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def add(self, **fields) -> QaEvent:
        event = QaEvent(**fields)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_recent(self, days: int = 30,
                    tenant_id: int | None = None) -> list[QaEvent]:
        since = datetime.now() - timedelta(days=days)
        query = self.db.query(QaEvent).filter(
            QaEvent.created_at >= since,
            QaEvent.handled.is_(False),
        )
        return (
            scoped(query, QaEvent, tenant_id)
            .order_by(QaEvent.created_at.desc())
            .all()
        )

    def mark_feedback(self, message_id: int, feedback: str,
                      tenant_id: int | None = None) -> None:
        query = self.db.query(QaEvent).filter(QaEvent.message_id == message_id)
        scoped(query, QaEvent, tenant_id).update(
            {QaEvent.feedback: feedback}, synchronize_session=False
        )
        self.db.commit()

    def mark_handled(self, queries: list[str],
                     tenant_id: int | None = None,
                     resolved_doc_id: int | None = None) -> int:
        """把某次缺口草稿覆盖的问题标记为已处理

        tenant_id 非空时只关闭该商家的缺口；resolved_doc_id 记录解决该缺口的
        FAQ 文档，后续据此做检索命中率回归。
        """
        if not queries:
            return 0
        query = self.db.query(QaEvent).filter(
            QaEvent.query.in_(queries), QaEvent.handled.is_(False)
        )
        values = {QaEvent.handled: True}
        if resolved_doc_id is not None:
            values[QaEvent.resolved_doc_id] = resolved_doc_id
        count = scoped(query, QaEvent, tenant_id).update(
            values, synchronize_session=False
        )
        self.db.commit()
        return count

    def list_resolved_queries(self, doc_id: int,
                              tenant_id: int | None = None) -> list[str]:
        """某篇 FAQ 发布时覆盖的原问题，用于命中率回归"""
        query = self.db.query(QaEvent.query).filter(
            QaEvent.resolved_doc_id == doc_id,
            QaEvent.handled.is_(True),
        )
        rows = scoped(query, QaEvent, tenant_id).distinct().all()
        return [row[0] for row in rows if row[0]]

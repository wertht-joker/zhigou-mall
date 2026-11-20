"""文档仓储"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.base import BaseRepository, apply_tenant, scoped


class DocumentRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def create(self, name: str, file_type: str, tenant_id: int | None = None,
               category_id: int | None = None,
               policy_key: str | None = None, version: int = 1,
               effective_from: datetime | None = None,
               effective_to: datetime | None = None,
               supersedes_id: int | None = None,
               lifecycle_status: str = "active") -> Document:
        doc = Document(
            name=name,
            type=file_type,
            size=0,
            chunk_count=0,
            status="processing",
            category_id=category_id,
            policy_key=policy_key,
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            supersedes_id=supersedes_id,
            lifecycle_status=lifecycle_status,
            created_at=datetime.now(),
        )
        apply_tenant(doc, tenant_id)
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get(self, doc_id: int, tenant_id: int | None = None) -> Document | None:
        query = scoped(self.db.query(Document).filter(Document.id == doc_id), Document, tenant_id)
        return query.first()

    def list(self, keyword: str | None = None, tenant_id: int | None = None) -> list[Document]:
        query = self.db.query(Document)
        if keyword:
            query = query.filter(Document.name.like(f"%{keyword}%"))
        query = scoped(query, Document, tenant_id)
        return query.order_by(Document.created_at.desc()).all()

    def latest_by_policy(self, policy_key: str,
                         tenant_id: int | None = None) -> Document | None:
        """同一政策标识下版本号最大的文档（用于自动递增版本）"""
        query = self.db.query(Document).filter(Document.policy_key == policy_key)
        query = scoped(query, Document, tenant_id)
        return query.order_by(Document.version.desc(), Document.id.desc()).first()

    def list_by_policy(self, policy_key: str,
                       tenant_id: int | None = None) -> list[Document]:
        """同一政策的全部历史版本（版本号倒序）"""
        query = self.db.query(Document).filter(Document.policy_key == policy_key)
        query = scoped(query, Document, tenant_id)
        return query.order_by(Document.version.desc(), Document.id.desc()).all()

    def supersede_policy(self, policy_key: str, tenant_id: int | None = None,
                         effective_to: datetime | None = None,
                         exclude_id: int | None = None) -> list[Document]:
        """把同一政策的 active 旧版本标记为 superseded，并补上失效时间。

        不物理删除：历史订单仍需要按旧版本回答，检索层用生效区间过滤。
        exclude_id 用于排除刚创建的新版本。
        """
        query = self.db.query(Document).filter(
            Document.policy_key == policy_key,
            Document.lifecycle_status == "active",
        )
        if exclude_id is not None:
            query = query.filter(Document.id != exclude_id)
        query = scoped(query, Document, tenant_id)
        old_docs = query.all()
        for doc in old_docs:
            doc.lifecycle_status = "superseded"
            if effective_to is not None and doc.effective_to is None:
                doc.effective_to = effective_to
        self.db.commit()
        return old_docs

    def save(self, doc: Document) -> Document:
        """提交对文档字段的修改并刷新"""
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def save_all(self, docs: list[Document]) -> None:
        """批量提交文档字段修改"""
        self.db.commit()
        for doc in docs:
            self.db.refresh(doc)

    def delete(self, doc: Document) -> None:
        self.db.delete(doc)
        self.db.commit()

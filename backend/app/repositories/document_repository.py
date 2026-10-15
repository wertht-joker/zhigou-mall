"""文档仓储"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.base import BaseRepository, apply_tenant, scoped


class DocumentRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def create(self, name: str, file_type: str, tenant_id: int | None = None) -> Document:
        doc = Document(
            name=name,
            type=file_type,
            size=0,
            chunk_count=0,
            status="processing",
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

    def save(self, doc: Document) -> Document:
        """提交对文档字段的修改并刷新"""
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def delete(self, doc: Document) -> None:
        self.db.delete(doc)
        self.db.commit()

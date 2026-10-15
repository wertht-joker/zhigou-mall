"""知识分类仓储"""
from sqlalchemy.orm import Session

from app.models.category import Category
from app.repositories.base import BaseRepository, apply_tenant, scoped


class CategoryRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def create(self, name: str, parent_id: int = 0, sort: int = 0,
               tenant_id: int | None = None) -> Category:
        category = Category(name=name, parent_id=parent_id, sort=sort)
        apply_tenant(category, tenant_id)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def get(self, category_id: int, tenant_id: int | None = None) -> Category | None:
        query = scoped(
            self.db.query(Category).filter(Category.id == category_id), Category, tenant_id
        )
        return query.first()

    def list(self, tenant_id: int | None = None) -> list[Category]:
        query = scoped(self.db.query(Category), Category, tenant_id)
        return query.order_by(Category.parent_id, Category.sort).all()

    def save(self, category: Category) -> Category:
        self.db.commit()
        self.db.refresh(category)
        return category

    def delete(self, category: Category) -> None:
        self.db.delete(category)
        self.db.commit()

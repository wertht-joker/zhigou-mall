"""知识分类服务"""
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.models.category import Category
from app.repositories.category_repository import CategoryRepository


def create_category(db: Session, name: str, parent_id: int = 0, sort: int = 0,
                    tenant_id: int | None = None) -> Category:
    if not name or not name.strip():
        raise BadRequestError("分类名称不能为空")
    return CategoryRepository(db).create(name.strip(), parent_id, sort, tenant_id)


def list_categories(db: Session, tenant_id: int | None = None) -> list[Category]:
    return CategoryRepository(db).list(tenant_id)


def update_category(db: Session, category_id: int, name: str | None = None,
                    parent_id: int | None = None, sort: int | None = None,
                    tenant_id: int | None = None) -> Category:
    repo = CategoryRepository(db)
    category = repo.get(category_id, tenant_id)
    if not category:
        raise NotFoundError("分类不存在")
    if name is not None:
        category.name = name
    if parent_id is not None:
        category.parent_id = parent_id
    if sort is not None:
        category.sort = sort
    return repo.save(category)


def delete_category(db: Session, category_id: int, tenant_id: int | None = None) -> None:
    repo = CategoryRepository(db)
    category = repo.get(category_id, tenant_id)
    if not category:
        raise NotFoundError("分类不存在")
    repo.delete(category)

"""用户仓储"""
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base import BaseRepository, apply_tenant, scoped


class UserRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def get(self, user_id: int, tenant_id: int | None = None) -> User | None:
        query = scoped(self.db.query(User).filter(User.id == user_id), User, tenant_id)
        return query.first()

    def get_by_username(self, username: str, tenant_id: int | None = None) -> User | None:
        query = scoped(self.db.query(User).filter(User.username == username), User, tenant_id)
        return query.first()

    def create(
        self,
        username: str,
        password_hash: str,
        role: str = "user",
        tenant_id: int | None = None,
    ) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        apply_tenant(user, tenant_id)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

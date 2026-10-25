"""收货地址仓储"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.address import Address
from app.repositories.base import BaseRepository


class AddressRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def list(self, user_id: int) -> list[Address]:
        return (
            self.db.query(Address)
            .filter(Address.user_id == user_id)
            .order_by(Address.is_default.desc(), Address.id.desc())
            .all()
        )

    def get(self, address_id: int, user_id: int) -> Address | None:
        return (
            self.db.query(Address)
            .filter(Address.id == address_id, Address.user_id == user_id)
            .first()
        )

    def create(self, **fields) -> Address:
        address = Address(**fields)
        self.db.add(address)
        self.db.commit()
        self.db.refresh(address)
        return address

    def save(self, address: Address) -> Address:
        self.db.commit()
        self.db.refresh(address)
        return address

    def delete(self, address: Address) -> None:
        self.db.delete(address)
        self.db.commit()

    def clear_default(self, user_id: int) -> None:
        """取消该顾客所有默认标记（设置新默认前调用）"""
        self.db.query(Address).filter(
            Address.user_id == user_id, Address.is_default.is_(True)
        ).update({"is_default": False}, synchronize_session=False)
        self.db.commit()

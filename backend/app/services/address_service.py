"""收货地址服务"""
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.address import Address
from app.repositories.address_repository import AddressRepository


def list_addresses(db: Session, user_id: int) -> list[Address]:
    return AddressRepository(db).list(user_id)


def create_address(db: Session, user_id: int, fields: dict) -> Address:
    repo = AddressRepository(db)
    if fields.get("is_default"):
        repo.clear_default(user_id)
    elif not repo.list(user_id):
        # 第一条地址自动设为默认
        fields["is_default"] = True
    return repo.create(**fields, user_id=user_id)


def update_address(db: Session, user_id: int, address_id: int, fields: dict) -> Address:
    repo = AddressRepository(db)
    address = _get_owned(repo, address_id, user_id)
    if fields.get("is_default"):
        repo.clear_default(user_id)
    for key, value in fields.items():
        setattr(address, key, value)
    return repo.save(address)


def delete_address(db: Session, user_id: int, address_id: int) -> None:
    repo = AddressRepository(db)
    address = _get_owned(repo, address_id, user_id)
    was_default = address.is_default
    repo.delete(address)
    if was_default:
        remaining = repo.list(user_id)
        if remaining:
            remaining[0].is_default = True
            repo.save(remaining[0])


def get_default(db: Session, user_id: int) -> Address | None:
    addresses = AddressRepository(db).list(user_id)
    return addresses[0] if addresses else None


def _get_owned(repo: AddressRepository, address_id: int, user_id: int) -> Address:
    address = repo.get(address_id, user_id)
    if not address:
        raise NotFoundError("地址不存在")
    return address

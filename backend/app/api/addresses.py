"""收货地址接口（登录顾客本人操作）"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import success
from app.models.database import get_db
from app.models.user import User
from app.schemas.address import AddressSaveRequest
from app.services import address_service

router = APIRouter(tags=["收货地址"])


def _serialize(address):
    return {k: v for k, v in address.__dict__.items() if not k.startswith("_")}


@router.get("/addresses")
def list_addresses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """我的地址簿"""
    return success([_serialize(a) for a in address_service.list_addresses(db, user.id)])


@router.post("/addresses")
def create_address(
    req: AddressSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """新增地址"""
    return success(
        _serialize(address_service.create_address(db, user.id, req.model_dump())),
        message="地址已保存",
    )


@router.put("/addresses/{address_id}")
def update_address(
    address_id: int,
    req: AddressSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改地址"""
    return success(
        _serialize(address_service.update_address(db, user.id, address_id, req.model_dump())),
        message="地址已更新",
    )


@router.delete("/addresses/{address_id}")
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除地址"""
    address_service.delete_address(db, user.id, address_id)
    return success(None, message="地址已删除")

"""文档管理接口（需 document:manage 权限）

业务失败由服务层抛 AppError，全局异常处理器负责输出 HTTP 状态码，
路由层不再需要 try/except。所有操作都在当前租户内进行。
"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, require_permission
from app.core.rate_limit import rate_limit
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.document import DocumentOut
from app.services import document_service

router = APIRouter(tags=["文档管理"])


@router.post("/documents/upload")
def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    _rate: None = Depends(rate_limit("upload")),
):
    """上传文档并入库（当前租户）"""
    doc = document_service.upload_document(db, file, tenant.id)
    return success(DocumentOut.model_validate(doc).model_dump(), message="文档入库成功")


@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    keyword: str = "",
):
    """文档列表，支持关键词搜索（仅当前租户）"""
    docs = document_service.list_documents(db, keyword or None, tenant.id)
    return success([DocumentOut.model_validate(d).model_dump() for d in docs])


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """删除文档（仅当前租户）"""
    document_service.delete_document(db, doc_id, tenant.id)
    return success(message="删除成功")

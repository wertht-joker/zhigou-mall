"""文档管理接口（需 document:manage 权限）

业务失败由服务层抛 AppError，全局异常处理器负责输出 HTTP 状态码，
路由层不再需要 try/except。默认在当前租户内操作；平台管理员可通过
tenant_id 查看/代管指定商家的知识库。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, require_permission
from app.core.errors import ForbiddenError
from app.core.rate_limit import rate_limit
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.document import DocumentOut, DocumentUpdateRequest
from app.services import document_service

router = APIRouter(tags=["文档管理"])


def _is_platform_admin(user: User) -> bool:
    return user.role == "platform_admin"


def _tenant_scope(user: User, tenant: Tenant,
                  requested: int | None) -> int | None:
    """解析本次操作的租户范围

    - 商家：只能操作自己的租户，传其他 tenant_id 直接拒绝；
    - 平台管理员：可按 tenant_id 代管任意商家，不传则跨租户查看。
    """
    if _is_platform_admin(user):
        return requested
    if requested is not None and requested != tenant.id:
        raise ForbiddenError("无权访问其他商家的知识库")
    return tenant.id


@router.post("/documents/upload")
def upload(
    file: UploadFile = File(...),
    category_id: int | None = Form(None),
    policy_key: str | None = Form(None),
    version: int | None = Form(None),
    effective_from: datetime | None = Form(None),
    effective_to: datetime | None = Form(None),
    tenant_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    _rate: None = Depends(rate_limit("upload")),
):
    """上传文档并入库（默认当前租户；平台管理员可指定商家）"""
    target_id = tenant.id
    if tenant_id is not None:
        if not _is_platform_admin(user) and tenant_id != tenant.id:
            raise ForbiddenError("无权向其他商家的知识库上传文档")
        target_id = tenant_id
    doc = document_service.upload_document(
        db, file, target_id,
        category_id=category_id,
        policy_key=policy_key,
        version=version,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    return success(DocumentOut.model_validate(doc).model_dump(), message="文档入库成功")


@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    keyword: str = "",
    tenant_id: int | None = Query(None, description="平台管理员按商家筛选"),
):
    """文档列表，支持关键词搜索；平台管理员可跨商家查看"""
    scope = _tenant_scope(user, tenant, tenant_id)
    docs = document_service.list_documents(db, keyword or None, scope)
    return success([DocumentOut.model_validate(d).model_dump() for d in docs])


@router.get("/documents/{doc_id}/versions")
def list_versions(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    tenant_id: int | None = Query(None),
):
    """查看某文档所属政策的全部历史版本"""
    scope = _tenant_scope(user, tenant, tenant_id)
    docs = document_service.list_versions(db, doc_id, scope)
    return success([DocumentOut.model_validate(d).model_dump() for d in docs])


@router.put("/documents/{doc_id}")
def update_document(
    doc_id: int,
    req: DocumentUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    tenant_id: int | None = Query(None),
):
    """编辑文档元数据（名称/分类/生效区间）"""
    scope = _tenant_scope(user, tenant, tenant_id)
    doc = document_service.update_document(
        db, doc_id, scope,
        name=req.name,
        category_id=req.category_id,
        effective_from=req.effective_from,
        effective_to=req.effective_to,
    )
    return success(DocumentOut.model_validate(doc).model_dump(), message="文档已更新")


@router.post("/documents/{doc_id}/activate")
def activate_version(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    tenant_id: int | None = Query(None),
):
    """把指定版本设为当前生效版本"""
    scope = _tenant_scope(user, tenant, tenant_id)
    doc = document_service.activate_version(db, doc_id, scope)
    return success(DocumentOut.model_validate(doc).model_dump(), message="已切换当前版本")


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:manage")),
    tenant: Tenant = Depends(get_current_tenant),
    tenant_id: int | None = Query(None),
):
    """删除文档（平台管理员可跨商家删除）"""
    scope = _tenant_scope(user, tenant, tenant_id)
    document_service.delete_document(db, doc_id, scope)
    return success(message="删除成功")

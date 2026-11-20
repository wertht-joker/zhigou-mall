"""平台管理接口（platform_admin 专属）

与商家后台的边界：
- 平台管理员只处理平台级数据：概览、商家、平台分类、全平台商品/订单监管；
- 商家后台的 /merchant/* 接口需要 product:manage / order:manage，
  platform_admin 不具备这些权限，因此两个后台在权限层彻底隔离。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.document import (
    KnowledgeGapDraftRequest,
    KnowledgeGapPublishRequest,
)
from app.schemas.product import ProductCategorySaveRequest
from app.schemas.user import TenantStatusRequest
from app.services import knowledge_gap_service, platform_service

router = APIRouter(prefix="/platform", tags=["平台管理"])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """平台数据概览"""
    return success(platform_service.overview(db))


@router.get("/insights")
def insights(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """智能运营洞察：经营脉搏、风险预警、商家健康度、知识缺口"""
    return success(platform_service.insights(db))


@router.get("/tenants")
def list_tenants(
    keyword: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """商家列表（含商品/订单统计）"""
    return success(platform_service.list_tenants(db, keyword))


@router.patch("/tenants/{tenant_id}/status")
def update_tenant_status(
    tenant_id: int,
    req: TenantStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """启用 / 停用商家"""
    data = platform_service.update_tenant_status(db, tenant_id, req.status)
    return success(data, message="商家状态已更新")


@router.get("/product-categories")
def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """平台商品分类（含分类下商品数）"""
    return success(platform_service.list_categories(db))


@router.post("/product-categories")
def create_category(
    req: ProductCategorySaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    data = platform_service.create_category(db, req.name, req.icon, req.sort)
    return success(data, message="分类已创建")


@router.put("/product-categories/{category_id}")
def update_category(
    category_id: int,
    req: ProductCategorySaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    data = platform_service.update_category(
        db, category_id, req.name, req.icon, req.sort
    )
    return success(data, message="分类已更新")


@router.delete("/product-categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    platform_service.delete_category(db, category_id)
    return success(message="分类已删除")


@router.get("/products")
def list_products(
    keyword: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """全平台商品监管（只读）"""
    return success(platform_service.list_products(db, keyword, status))


@router.get("/orders")
def list_orders(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """全平台订单监管（只读）"""
    return success(platform_service.list_orders(db, status, limit))


@router.get("/customers")
def list_customers(
    keyword: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """顾客管理（账号与消费概况）"""
    return success(platform_service.list_customers(db, keyword))


@router.get("/feedback")
def feedback_overview(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """AI 客服反馈分析"""
    return success(platform_service.feedback_overview(db, limit))


@router.get("/audit-logs")
def audit_logs(
    result: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """售后 Agent 写操作审计日志"""
    return success(platform_service.list_audit_logs(db, limit, result))


@router.get("/knowledge-gaps")
def knowledge_gaps(
    days: int = 30,
    tenant_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """知识缺口看板：按商家隔离后的缺口主题与影响面"""
    return success(knowledge_gap_service.list_gaps(db, days, tenant_id))


@router.post("/knowledge-gaps/draft")
def knowledge_gap_draft(
    req: KnowledgeGapDraftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """根据缺口问题生成带证据指针的 FAQ 草稿"""
    return success(knowledge_gap_service.build_draft(
        db, req.queries, req.tenant_id
    ))


@router.post("/knowledge-gaps/publish")
def knowledge_gap_publish(
    req: KnowledgeGapPublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """把 FAQ 发布到指定商家知识库，关闭该商家缺口并做命中率回归"""
    owner_id = req.tenant_id if req.tenant_id is not None else tenant.id
    return success(knowledge_gap_service.publish_draft(
        db, req.title, req.content, req.queries, req.category_id,
        tenant_id=owner_id,
    ))


@router.get("/knowledge-gaps/regression/{doc_id}")
def knowledge_gap_regression(
    doc_id: int,
    tenant_id: int | None = None,
    top_k: int = 5,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("platform:manage")),
):
    """重新跑某篇 FAQ 的命中率回归"""
    return success(knowledge_gap_service.run_regression(
        db, doc_id, tenant_id, top_k
    ))

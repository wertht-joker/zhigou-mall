"""售后 Agent 接口：确认执行 / 取消提案 / 我的售后工单

写操作不经过模型：模型只生成提案（见 tools.propose_after_sales_action），
这里是由用户点击"确认"触发的独立接口，令牌一次性、与登录用户和会话绑定。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.aftersale import CancelActionRequest, ConfirmActionRequest
from app.services import aftersale_service

router = APIRouter(tags=["售后 Agent"])


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "") or ""


@router.post("/aftersale/actions/{token}/confirm")
def confirm_action(
    token: str,
    req: ConfirmActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认执行售后提案（重复确认返回首次结果，不会重复执行）"""
    result = aftersale_service.confirm(
        db, user.id, req.session_id, token, req.idempotency_key, _trace_id(request)
    )
    return success(result, message=result["message"])


@router.post("/aftersale/actions/{token}/cancel")
def cancel_action(
    token: str,
    req: CancelActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """取消本次售后提案（不产生任何业务变更）"""
    result = aftersale_service.cancel_proposal(db, user.id, req.session_id, token)
    return success(result, message=result["message"])


@router.get("/aftersale/tickets")
def list_my_tickets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的售后工单（退款申请）"""
    return success(aftersale_service.list_my_tickets(db, user.id))


# ===== 商家审核 =====

@router.get("/merchant/aftersale/tickets")
def list_merchant_tickets(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("order:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """商家售后工单列表：只含包含本店商品的订单"""
    return success(aftersale_service.list_merchant_tickets(db, tenant.id, status))


@router.post("/merchant/aftersale/tickets/{ticket_id}/approve")
def approve_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("order:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """通过退款申请：工单 → 已完成"""
    result = aftersale_service.review_ticket(
        db, ticket_id, tenant.id, user.id, True, _trace_id(request)
    )
    return success(result, message="已通过退款申请")


@router.post("/merchant/aftersale/tickets/{ticket_id}/reject")
def reject_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("order:manage")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """驳回退款申请：工单 → 已驳回"""
    result = aftersale_service.review_ticket(
        db, ticket_id, tenant.id, user.id, False, _trace_id(request)
    )
    return success(result, message="已驳回退款申请")

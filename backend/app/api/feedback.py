"""反馈接口（需登录）

- POST /feedback       任意登录用户可提交反馈（按租户隔离）
- GET  /feedback/stats 需 feedback:view 权限（默认 admin）
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user, require_permission
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.feedback import FeedbackCreate
from app.services import feedback_service

router = APIRouter(tags=["反馈"])


@router.post("/feedback")
def add_feedback(
    req: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """回答反馈（type: up 有用 / down 无用）"""
    feedback_service.add_feedback(db, req.message_id, req.type, tenant.id)
    return success(message="反馈成功")


@router.get("/feedback/stats")
def stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("feedback:view")),
    tenant: Tenant = Depends(get_current_tenant),
):
    """反馈统计（仅当前租户）"""
    return success(feedback_service.stats(db, tenant.id))

"""智能问答接口（需登录，按租户隔离）"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_current_user
from app.core.rate_limit import rate_limit
from app.core.response import success
from app.models.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services import chat_service

router = APIRouter(tags=["智能问答"])


@router.post("/chat/stream")
def chat_stream(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    _rate: None = Depends(rate_limit("chat")),
):
    """流式问答（SSE，答案逐字输出）

    建流前的鉴权/参数错误仍以普通 JSON 4xx 返回（由全局异常处理器产出），
    前端需先判断 resp.ok 再读取流。
    """
    return StreamingResponse(
        chat_service.ask_stream(db, req.question, req.session_id, tenant.id, user.id),
        media_type="text/event-stream",
    )


@router.post("/chat")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    _rate: None = Depends(rate_limit("chat")),
):
    """提问并获取带引用来源的答案（知识库按商家隔离，订单工具按用户隔离）"""
    resp = chat_service.ask(db, req.question, req.session_id, tenant.id, user.id)
    return success(resp.model_dump())

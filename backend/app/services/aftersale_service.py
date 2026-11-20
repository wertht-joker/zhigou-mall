"""售后 Agent 服务：提议 → 确认 → 执行 + 幂等 / 补偿 / 审计

【为什么写操作不能交给模型直接执行】
  大模型的输出是概率性的，可能被提示注入、也可能"好心"理解错订单。
  因此模型只拿到 propose 工具：它生成一条 *提案*，不改任何业务数据；
  用户在界面上看到卡片并点击"确认执行"后，才由独立接口带着一次性令牌真正落库。
  令牌与 user_id / session_id / 参数摘要 / 有效期绑定，任何一项对不上都拒绝。

【幂等】（同一确认只执行一次）
  1. pending_actions.used_at 由条件更新（WHERE used_at IS NULL）抢占，
     只有影响行数 = 1 的请求能进入执行，并发重复确认全部落到回放分支；
  2. 首次执行结果写入 result_json，重复确认原样返回（前端重试不会重复取消/退款）；
  3. 可选幂等键 idempotency_key 唯一约束，跨提案的客户端重试也能识别。

【补偿】（主操作成功、逆向动作失败怎么办）
  取消订单 = 状态流转 + 回补库存 + 退回优惠券。状态流转用条件更新保证原子，
  后两个动作若失败，写入 compensation_tasks 供后台重试/对账，绝不吞掉异常。

【审计】
  每次执行（成功/部分成功/失败）都写 action_audit_logs：
  actor / action / target / before / after / trace_id。
"""
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AppError,
    AppServiceError,
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from app.models.aftersale import (
    ACTION_CANCEL_ORDER,
    ACTION_CHANGE_ADDRESS,
    ACTION_CREATE_REFUND,
    ACTION_STATUS_CANCELLED,
    ACTION_STATUS_CONFIRMED,
    ACTION_STATUS_EXPIRED,
    ACTION_STATUS_FAILED,
    ACTION_STATUS_PENDING,
    ACTION_TYPES,
    TICKET_DONE,
    TICKET_PENDING,
    TICKET_REJECTED,
    AfterSalesTicket,
    PendingAction,
)
from app.models.order import (
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_DONE,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_SHIPPED,
    Order,
)
from app.repositories.address_repository import AddressRepository
from app.repositories.aftersale_repository import AfterSaleRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.services import coupon_service, product_service

logger = logging.getLogger("app.aftersale")

# 确认令牌有效期（分钟）
ACTION_TTL_MINUTES = 5


def _canonical(params: dict) -> str:
    """规范化 JSON：键排序 + 紧凑分隔符，保证同一参数永远得到同一摘要"""
    return json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_params(params_json: str) -> str:
    return hashlib.sha256(params_json.encode("utf-8")).hexdigest()


def _gen_ticket_no() -> str:
    return f"RF{datetime.now():%Y%m%d%H%M%S}{secrets.randbelow(10000):04d}"


def _serialize_action(action: PendingAction) -> dict:
    return {
        "token": action.token,
        "action_type": action.action_type,
        "title": ACTION_TYPES.get(action.action_type, "售后操作"),
        "summary": action.summary,
        "details": json.loads(action.details_json or "[]"),
        "expires_at": action.expires_at.isoformat(timespec="seconds"),
    }


def _get_owned_order(db: Session, user_id: int, order_no: str) -> Order:
    """按订单号取本人订单；不存在与越权统一 404（不泄露他人订单存在性）"""
    order = OrderRepository(db).get_by_order_no(order_no)
    if not order or order.user_id != user_id:
        raise NotFoundError("订单不存在")
    return order


def _clean_order_no(value) -> str:
    order_no = str(value or "").strip()
    if not order_no:
        raise BadRequestError("缺少订单号")
    return order_no


def _prepare(db: Session, user_id: int, action_type: str,
             raw: dict) -> tuple[dict, str, list[dict]]:
    """校验并规范化参数（提议时做一次，确认时再验一次，防 TOCTOU）

    返回 (规范化参数, 卡片摘要, 卡片明细)。所有校验读操作，不产生任何写入。
    """
    raw = raw or {}

    if action_type == ACTION_CANCEL_ORDER:
        order_no = _clean_order_no(raw.get("order_no"))
        order = _get_owned_order(db, user_id, order_no)
        if order.status != ORDER_STATUS_PENDING:
            raise BadRequestError(
                f"订单 {order_no} 当前状态为「{order.status}」，仅待付款订单可以取消"
            )
        params = {"order_no": order_no}
        summary = (
            f"取消订单 {order_no}（¥{order.total_amount:g}），"
            f"库存与已使用的优惠券将自动退回"
        )
        details = [
            {"label": "订单号", "value": order_no},
            {"label": "订单状态", "value": order.status},
            {"label": "订单金额", "value": f"¥{order.total_amount:g}"},
        ]
        return params, summary, details

    if action_type == ACTION_CREATE_REFUND:
        order_no = _clean_order_no(raw.get("order_no"))
        reason = str(raw.get("reason") or "").strip()
        if len(reason) < 2:
            raise BadRequestError("请说明退款原因（至少 2 个字）")
        order = _get_owned_order(db, user_id, order_no)
        if order.status not in (ORDER_STATUS_PAID, ORDER_STATUS_SHIPPED, ORDER_STATUS_DONE):
            if order.status == ORDER_STATUS_PENDING:
                raise BadRequestError(
                    f"订单 {order_no} 尚未支付，无需退款，可以直接取消订单"
                )
            raise BadRequestError(
                f"订单 {order_no} 当前状态为「{order.status}」，不可申请退款"
            )
        if AfterSaleRepository(db).has_open_ticket(order.id):
            raise BadRequestError(f"订单 {order_no} 已有处理中的售后单，请勿重复申请")
        params = {"order_no": order_no, "reason": reason[:200]}
        summary = (
            f"为订单 {order_no} 提交退款申请（¥{order.total_amount:g}），"
            f"原因：{reason[:40]}"
        )
        details = [
            {"label": "订单号", "value": order_no},
            {"label": "订单状态", "value": order.status},
            {"label": "退款金额", "value": f"¥{order.total_amount:g}"},
            {"label": "退款原因", "value": reason[:200]},
        ]
        return params, summary, details

    if action_type == ACTION_CHANGE_ADDRESS:
        order_no = _clean_order_no(raw.get("order_no"))
        try:
            address_id = int(raw.get("address_id"))
        except (TypeError, ValueError):
            raise BadRequestError("请提供要修改到的收货地址")
        order = _get_owned_order(db, user_id, order_no)
        if order.status not in (ORDER_STATUS_PENDING, ORDER_STATUS_PAID):
            raise BadRequestError(
                f"订单 {order_no} 当前状态为「{order.status}」，发货后不可修改收货地址"
            )
        address = AddressRepository(db).get(address_id, user_id)
        if not address:
            raise NotFoundError("收货地址不存在")
        new_address = f"{address.region} {address.detail}".strip()
        params = {"order_no": order_no, "address_id": address_id}
        summary = (
            f"将订单 {order_no} 的收货地址改为："
            f"{address.receiver} {address.phone} {new_address}"
        )
        details = [
            {"label": "订单号", "value": order_no},
            {"label": "原收货信息", "value": f"{order.receiver_name} {order.receiver_phone} {order.receiver_address}"},
            {"label": "新收货信息", "value": f"{address.receiver} {address.phone} {new_address}"},
        ]
        return params, summary, details

    raise BadRequestError("不支持的售后操作类型")


def propose(db: Session, user_id: int, session_id: int, action_type: str,
            raw_params: dict) -> dict:
    """生成待确认提案（唯一入口，模型只能调到这里）

    返回值会作为 action 卡片随 SSE 推给前端；token 是唯一凭据，不包含权限信息。
    """
    if action_type not in ACTION_TYPES:
        raise BadRequestError("不支持的售后操作类型")

    params, summary, details = _prepare(db, user_id, action_type, raw_params)
    params_json = _canonical(params)
    action = AfterSaleRepository(db).create_action(
        token=secrets.token_urlsafe(32),
        user_id=user_id,
        session_id=session_id,
        action_type=action_type,
        params_json=params_json,
        params_hash=_hash_params(params_json),
        summary=summary[:255],
        details_json=json.dumps(details, ensure_ascii=False),
        status=ACTION_STATUS_PENDING,
        expires_at=datetime.now() + timedelta(minutes=ACTION_TTL_MINUTES),
    )
    return _serialize_action(action)


def cancel_proposal(db: Session, user_id: int, session_id: int, token: str) -> dict:
    """用户放弃本次操作：只改提案状态，不触碰业务数据"""
    repo = AfterSaleRepository(db)
    action = repo.get_by_token(token)
    if not action or action.user_id != user_id:
        raise NotFoundError("操作不存在或已失效")
    if action.session_id != session_id:
        raise BadRequestError("该操作不属于当前会话")
    if action.status != ACTION_STATUS_PENDING or action.used_at is not None:
        raise BadRequestError("该操作已执行或已失效，无法取消")
    action.status = ACTION_STATUS_CANCELLED
    repo.save(action)
    return {"token": token, "status": "cancelled", "message": "已取消，未产生任何变更"}


def _replay(action: PendingAction) -> dict:
    """重复确认：原样回放首次结果（幂等读路径）"""
    data = json.loads(action.result_json or "{}")
    return {**data, "replayed": True}


def _target_of(action: PendingAction, params: dict, result: dict) -> tuple[str, str]:
    if action.action_type == ACTION_CREATE_REFUND:
        return "after_sales_ticket", str(result.get("ticket_no") or params.get("order_no", ""))
    return "order", str(params.get("order_no", ""))


def _audit(db: Session, trace_id: str, user_id: int, action: PendingAction,
           before: dict, after: dict, result: str, error: str = "",
           extra: dict | None = None) -> None:
    """写审计日志；审计失败只记应用日志，不反向推翻已成功的业务操作"""
    try:
        params = json.loads(action.params_json or "{}")
        target_type, target_id = _target_of(action, params, extra or {})
        AfterSaleRepository(db).add_audit(
            trace_id=trace_id or "",
            user_id=user_id,
            action_type=action.action_type,
            target_type=target_type,
            target_id=target_id,
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(after, ensure_ascii=False),
            result=result,
            error=error[:255],
        )
    except Exception:
        logger.exception("写审计日志失败 action_id=%s", action.id)


def _finish_failed(db: Session, trace_id: str, user_id: int, action: PendingAction,
                   message: str, before: dict | None = None) -> None:
    payload = {
        "message": message,
        "error": message,
        "action_type": action.action_type,
    }
    AfterSaleRepository(db).finish(
        action.id, ACTION_STATUS_FAILED, json.dumps(payload, ensure_ascii=False)
    )
    _audit(db, trace_id, user_id, action, before or {}, {}, "failed", message)


def _restore_stock_safe(db: Session, action: PendingAction, user_id: int,
                        order: Order) -> dict:
    """回补库存；失败落补偿任务（已提交的订单状态不会回滚）"""
    try:
        restored = []
        for item in OrderRepository(db).items_of(order.id):
            if not item.product_id:
                continue
            if not ProductRepository(db).get(item.product_id):
                continue
            product_service.restore_item_stock(
                db, item.product_id, item.variant_id, item.quantity
            )
            restored.append({
                "product_id": item.product_id,
                "variant_id": item.variant_id,
                "quantity": item.quantity,
            })
        db.commit()
        return {"ok": True, "items": restored}
    except Exception as exc:
        db.rollback()
        logger.exception("取消订单回补库存失败 order_no=%s", order.order_no)
        AfterSaleRepository(db).add_compensation(
            action_id=action.id,
            user_id=user_id,
            task_type="restore_stock",
            payload_json=json.dumps(
                {"order_id": order.id, "order_no": order.order_no}, ensure_ascii=False
            ),
            error=str(exc)[:255],
        )
        return {"ok": False, "error": str(exc)}


def _release_coupon_safe(db: Session, action: PendingAction, user_id: int,
                         order: Order) -> dict:
    """退回优惠券；失败落补偿任务"""
    try:
        coupon_service.release_if_any(db, order.id)
        return {"ok": True}
    except Exception as exc:
        db.rollback()
        logger.exception("取消订单退回优惠券失败 order_no=%s", order.order_no)
        AfterSaleRepository(db).add_compensation(
            action_id=action.id,
            user_id=user_id,
            task_type="release_coupon",
            payload_json=json.dumps(
                {"order_id": order.id, "order_no": order.order_no}, ensure_ascii=False
            ),
            error=str(exc)[:255],
        )
        return {"ok": False, "error": str(exc)}


def _execute_cancel(db: Session, action: PendingAction, user_id: int,
                    params: dict) -> tuple[dict, dict, dict, list]:
    order = _get_owned_order(db, user_id, params["order_no"])
    if order.status != ORDER_STATUS_PENDING:
        raise BadRequestError(
            f"订单 {order.order_no} 当前状态为「{order.status}」，取消未执行"
        )
    before = {
        "order_no": order.order_no,
        "status": order.status,
        "total_amount": order.total_amount,
    }

    # 条件更新：只有仍是"待付款"时才取消，影响行数 = 1 才算真正抢到
    rows = (
        db.query(Order)
        .filter(Order.id == order.id, Order.status == ORDER_STATUS_PENDING)
        .update({"status": ORDER_STATUS_CANCELLED}, synchronize_session=False)
    )
    db.commit()
    if rows != 1:
        raise BadRequestError("订单状态已变化（可能已支付或已取消），本次未执行")

    warnings = []
    stock = _restore_stock_safe(db, action, user_id, order)
    if not stock["ok"]:
        warnings.append({"type": "restore_stock", "message": "库存回补失败，已登记补偿任务"})
    coupon = _release_coupon_safe(db, action, user_id, order)
    if not coupon["ok"]:
        warnings.append({"type": "release_coupon", "message": "优惠券退回失败，已登记补偿任务"})

    message = f"订单 {order.order_no} 已取消，库存与优惠券已同步退回"
    if warnings:
        message = f"订单 {order.order_no} 已取消，但部分补偿未完成，已登记补偿任务"
    result = {
        "message": message,
        "status": "已取消",
        "order_no": order.order_no,
        "stock_restored": stock["ok"],
        "coupon_released": coupon["ok"],
        "warnings": warnings,
    }
    after = {
        "order_no": order.order_no,
        "status": ORDER_STATUS_CANCELLED,
        "stock_restored": stock.get("items", []),
        "coupon_released": coupon["ok"],
        "compensations": [w["type"] for w in warnings],
    }
    return result, before, after, warnings


def _execute_refund(db: Session, action: PendingAction, user_id: int,
                    params: dict) -> tuple[dict, dict, dict, list]:
    repo = AfterSaleRepository(db)
    order = _get_owned_order(db, user_id, params["order_no"])
    if order.status not in (ORDER_STATUS_PAID, ORDER_STATUS_SHIPPED, ORDER_STATUS_DONE):
        raise BadRequestError(
            f"订单 {order.order_no} 当前状态为「{order.status}」，不可申请退款"
        )
    if repo.has_open_ticket(order.id):
        raise BadRequestError(f"订单 {order.order_no} 已有处理中的售后单，请勿重复申请")

    ticket = repo.create_ticket(
        ticket_no=_gen_ticket_no(),
        user_id=user_id,
        order_id=order.id,
        order_no=order.order_no,
        kind="退款",
        amount=order.total_amount,
        reason=params["reason"],
        status=TICKET_PENDING,
    )
    result = {
        "message": f"退款申请已提交，工单号 {ticket.ticket_no}，商家将在 1-3 个工作日内处理",
        "ticket_no": ticket.ticket_no,
        "status": ticket.status,
        "amount": ticket.amount,
        "order_no": ticket.order_no,
    }
    before = {"order_no": order.order_no, "ticket": None}
    after = {
        "ticket_no": ticket.ticket_no,
        "order_no": ticket.order_no,
        "amount": ticket.amount,
        "reason": ticket.reason,
        "status": ticket.status,
    }
    return result, before, after, []


def _execute_change_address(db: Session, action: PendingAction, user_id: int,
                            params: dict) -> tuple[dict, dict, dict, list]:
    order = _get_owned_order(db, user_id, params["order_no"])
    if order.status not in (ORDER_STATUS_PENDING, ORDER_STATUS_PAID):
        raise BadRequestError(
            f"订单 {order.order_no} 当前状态为「{order.status}」，发货后不可修改收货地址"
        )
    address = AddressRepository(db).get(params["address_id"], user_id)
    if not address:
        raise NotFoundError("收货地址不存在")

    before = {
        "order_no": order.order_no,
        "receiver_name": order.receiver_name,
        "receiver_phone": order.receiver_phone,
        "receiver_address": order.receiver_address,
    }
    new_address = f"{address.region} {address.detail}".strip()
    rows = (
        db.query(Order)
        .filter(
            Order.id == order.id,
            Order.status.in_([ORDER_STATUS_PENDING, ORDER_STATUS_PAID]),
        )
        .update(
            {
                "receiver_name": address.receiver,
                "receiver_phone": address.phone,
                "receiver_address": new_address,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if rows != 1:
        raise BadRequestError("订单状态已变化，收货地址未修改")

    after = {
        "order_no": order.order_no,
        "receiver_name": address.receiver,
        "receiver_phone": address.phone,
        "receiver_address": new_address,
    }
    result = {
        "message": f"订单 {order.order_no} 的收货地址已更新为：{address.receiver} {address.phone} {new_address}",
        "order_no": order.order_no,
        "receiver_name": address.receiver,
        "receiver_phone": address.phone,
        "receiver_address": new_address,
    }
    return result, before, after, []


_EXECUTORS = {
    ACTION_CANCEL_ORDER: _execute_cancel,
    ACTION_CREATE_REFUND: _execute_refund,
    ACTION_CHANGE_ADDRESS: _execute_change_address,
}


def confirm(db: Session, user_id: int, session_id: int, token: str,
            idempotency_key: str | None = None, trace_id: str = "") -> dict:
    """确认并执行提案（唯一写入口）

    校验顺序刻意从"身份/会话/时效/参数"到"抢占执行权"：
    前四步都是只读校验，最后一步的条件更新才是并发闸门。
    """
    repo = AfterSaleRepository(db)
    action = repo.get_by_token(token)
    if not action or action.user_id != user_id:
        # 越权与不存在统一 404，不泄露 token 是否存在
        raise NotFoundError("操作不存在或已失效")
    if action.session_id != session_id:
        raise BadRequestError("该操作不属于当前会话，请重新发起")

    # 已执行过 → 回放首次结果（重复点击/网络重试不会再执行一次）
    if action.result_json:
        return _replay(action)
    if action.used_at is not None:
        raise ConflictError("操作正在执行，请稍后刷新")
    if action.status == ACTION_STATUS_CANCELLED:
        raise BadRequestError("该操作已取消")
    if action.status == ACTION_STATUS_EXPIRED:
        raise BadRequestError("确认已过期，请让助手重新发起")
    if datetime.now() > action.expires_at:
        action.status = ACTION_STATUS_EXPIRED
        repo.save(action)
        raise BadRequestError(f"确认已过期（{ACTION_TTL_MINUTES} 分钟内有效），请让助手重新发起")

    # 参数摘要比对：即使有人改了库里的参数，也无法让确认接口执行另一组参数
    if _hash_params(action.params_json) != action.params_hash:
        raise BadRequestError("操作参数校验失败，请重新发起")

    if idempotency_key:
        existing = repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.id != action.id:
            raise ConflictError("幂等键已被其他操作使用")

    try:
        rows = repo.claim(action.id, idempotency_key)
    except IntegrityError:
        db.rollback()
        raise ConflictError("幂等键已被其他操作使用")
    if rows == 0:
        # 被并发请求抢先：等它写完结果后回放；还没写完就提示稍后刷新
        db.expire_all()
        current = repo.get_by_token(token)
        if current and current.result_json:
            return _replay(current)
        raise ConflictError("操作正在执行，请稍后刷新")

    params = json.loads(action.params_json)
    before: dict = {}
    try:
        result, before, after, warnings = _EXECUTORS[action.action_type](
            db, action, user_id, params
        )
    except AppError as exc:
        _finish_failed(db, trace_id, user_id, action, exc.message, before)
        raise
    except Exception as exc:
        logger.exception("售后操作执行异常 action_id=%s", action.id)
        _finish_failed(
            db, trace_id, user_id, action, "操作执行失败，请稍后重试或联系人工客服", before
        )
        raise AppServiceError("操作执行失败，请稍后重试") from exc

    payload = {**result, "action_type": action.action_type}
    repo.finish(
        action.id, ACTION_STATUS_CONFIRMED, json.dumps(payload, ensure_ascii=False)
    )
    _audit(
        db, trace_id, user_id, action, before, after,
        "partial" if warnings else "success", "", result,
    )
    return {**payload, "replayed": False}


def _serialize_ticket(ticket: AfterSalesTicket) -> dict:
    """工单对外结构（顾客端"我的售后"与商家端审核列表共用）"""
    return {
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "order_no": ticket.order_no,
        "kind": ticket.kind,
        "amount": ticket.amount,
        "reason": ticket.reason,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


def list_my_tickets(db: Session, user_id: int) -> list[dict]:
    """我的售后工单（给演示/对账用）"""
    return [
        _serialize_ticket(t)
        for t in AfterSaleRepository(db).list_tickets(user_id)
    ]


def list_merchant_tickets(db: Session, merchant_id: int,
                          status: str | None = None) -> list[dict]:
    """商家待办：只返回包含本店商品的订单所对应的售后工单"""
    return [
        _serialize_ticket(t)
        for t in AfterSaleRepository(db).list_merchant_tickets(merchant_id, status)
    ]


def review_ticket(db: Session, ticket_id: int, merchant_id: int, user_id: int,
                  approve: bool, trace_id: str = "") -> dict:
    """商家审核退款工单：通过 → 已完成，驳回 → 已驳回

    【越权】不属于本店商品的工单统一 404，不泄露工单是否存在；
    【重复审核】用状态条件更新（WHERE status='待商家处理'）抢占，
               两个商家账号同时点击也只有一次生效；
    【审计】审核是写操作，记录 actor / before / after / trace_id。
    """
    repo = AfterSaleRepository(db)
    ticket = repo.get_ticket(ticket_id)
    if not ticket or not repo.ticket_belongs_to_merchant(ticket, merchant_id):
        raise NotFoundError("售后单不存在")

    target = TICKET_DONE if approve else TICKET_REJECTED
    before = {"ticket_no": ticket.ticket_no, "status": ticket.status}
    rows = repo.transition_ticket(ticket.id, TICKET_PENDING, target)
    if rows != 1:
        raise BadRequestError("该售后单已处理，请勿重复操作")

    db.refresh(ticket)
    after = {"ticket_no": ticket.ticket_no, "status": ticket.status}
    try:
        repo.add_audit(
            trace_id=trace_id or "",
            user_id=user_id,
            action_type="review_after_sales_ticket",
            target_type="after_sales_ticket",
            target_id=ticket.ticket_no,
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(after, ensure_ascii=False),
            result="success",
        )
    except Exception:
        # 审计失败不推翻已完成的业务操作，只记录应用日志
        logger.exception("写审核审计失败 ticket_id=%s", ticket.id)

    return _serialize_ticket(ticket)

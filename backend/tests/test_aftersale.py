"""可执行售后 Agent 测试

覆盖点与答辩/论文里的"写操作事务协议"一一对应：
- 提议不产生任何副作用（订单/库存/券/审计都未变）
- 确认后真正执行，并完成库存回补、优惠券退回
- 重复确认幂等（回放首次结果，不重复回补）
- 过期 / 他人 / 换会话 / 参数篡改 一律拒绝
- 退款工单、改址规则
- 补偿任务与审计日志落库

运行：在 backend 目录执行 pytest -q -k aftersale
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1"


# ===== 夹具 =====

@pytest.fixture
def buyer_token(client, make_user):
    make_user("buyer", "buyer123", "customer")
    return _login(client, "buyer", "buyer123")


@pytest.fixture
def buyer2_token(client, make_user):
    make_user("buyer2", "buyer2123", "customer")
    return _login(client, "buyer2", "buyer2123")


@pytest.fixture
def product_id(engine):
    """一件库存 10、单价 100 的在售商品"""
    from app.models.product import Product
    from app.services import tenant_service

    session = _db(engine)
    try:
        tenant = tenant_service.ensure_default_tenant(session)
        product = Product(
            tenant_id=tenant.id, name="售后测试商品", subtitle="",
            description="", price=100.0, stock=10, sales=0,
            image="📦", status="on_sale",
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        return product.id
    finally:
        session.close()


@pytest.fixture
def address_id(client, buyer_token):
    resp = client.post(f"{BASE}/addresses", headers=buyer_token, json={
        "receiver": "李雷", "phone": "13800138000",
        "region": "北京市 朝阳区", "detail": "幸福小区 3 号楼 201", "is_default": True,
    })
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def _db(engine):
    return sessionmaker(bind=engine)()


def _login(client, username: str, password: str) -> dict:
    resp = client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    return {"Authorization": "Bearer " + resp.json()["data"]["token"]}


def _user_id(engine, username: str) -> int:
    from app.models.user import User

    session = _db(engine)
    try:
        return session.query(User).filter(User.username == username).first().id
    finally:
        session.close()


def _create_order(client, token, product_id, address_id,
                  quantity=2, coupon_id=None, pay=False):
    """加购 + 下单（可选支付），返回订单数据"""
    client.post(f"{BASE}/cart/items", headers=token,
                json={"product_id": product_id, "quantity": quantity})
    payload = {"address_id": address_id}
    if coupon_id:
        payload["coupon_id"] = coupon_id
    resp = client.post(f"{BASE}/orders", headers=token, json=payload)
    assert resp.status_code == 200, resp.text
    order = resp.json()["data"]
    if pay:
        resp = client.post(f"{BASE}/orders/{order['id']}/pay", headers=token)
        assert resp.status_code == 200
        order["status"] = "待发货"
    return order


def _propose(engine, username, order_no, action_type="cancel_order",
             params=None, session_id=1):
    from app.services import aftersale_service

    session = _db(engine)
    try:
        return aftersale_service.propose(
            session, _user_id(engine, username), session_id, action_type,
            params or {"order_no": order_no},
        )
    finally:
        session.close()


def _confirm(client, headers, action_token, session_id=1):
    return client.post(
        f"{BASE}/aftersale/actions/{action_token}/confirm",
        headers=headers,
        json={"session_id": session_id},
    )


# ===== 提议：只读，不产生副作用 =====

def test_propose_has_no_side_effect(client, buyer_token, product_id, address_id, engine):
    from app.models.aftersale import ActionAuditLog, PendingAction
    from app.models.order import Order
    from app.models.product import Product

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    assert proposal["token"]
    assert proposal["title"] == "取消订单"
    assert order["order_no"] in proposal["summary"]
    assert proposal["details"][0] == {"label": "订单号", "value": order["order_no"]}

    session = _db(engine)
    try:
        assert session.query(Order).filter(Order.id == order["id"]).first().status == "待付款"
        assert session.query(Product).filter(Product.id == product_id).first().stock == 8
        assert session.query(PendingAction).count() == 1
        assert session.query(ActionAuditLog).count() == 0  # 提议不是写操作，不写审计
    finally:
        session.close()


def test_agent_tool_only_proposes(client, buyer_token, product_id, address_id, engine):
    """Agent 工具返回 action 卡片，但订单状态不变；编造订单号只得到话术"""
    from app.models.order import Order
    from app.services import tools

    order = _create_order(client, buyer_token, product_id, address_id)
    uid = _user_id(engine, "buyer")
    session = _db(engine)
    try:
        result = tools.execute_tool(
            "propose_after_sales_action",
            {"action_type": "cancel_order", "order_no": order["order_no"]},
            session, None, uid, 1,
        )
        assert result.payload["type"] == "action"
        assert result.payload["action"]["action_type"] == "cancel_order"
        assert "确认" in result.text

        fake = tools.execute_tool(
            "propose_after_sales_action",
            {"action_type": "cancel_order", "order_no": "ZG-FAKE-000"},
            session, None, uid, 1,
        )
        assert fake.payload is None
        assert "无法发起" in fake.text
        assert session.query(Order).filter(Order.id == order["id"]).first().status == "待付款"
    finally:
        session.close()


# ===== 确认：执行 + 补偿 + 审计 =====

def test_confirm_cancel_restores_stock_and_coupon(client, buyer_token, product_id,
                                                  address_id, engine):
    from app.models.aftersale import ActionAuditLog, PendingAction
    from app.models.coupon import Coupon
    from app.models.order import Order
    from app.models.product import Product

    # 领 199-30 券，下单 300 元用券（应付 270）
    resp = client.post(f"{BASE}/coupons/claim", headers=buyer_token, json={"threshold": 199})
    assert resp.status_code == 200
    coupon_id = resp.json()["data"]["id"]
    order = _create_order(client, buyer_token, product_id, address_id,
                          quantity=3, coupon_id=coupon_id)
    assert order["total_amount"] == 270.0

    proposal = _propose(engine, "buyer", order["order_no"])
    resp = _confirm(client, buyer_token, proposal["token"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["replayed"] is False
    assert data["status"] == "已取消"
    assert data["stock_restored"] is True
    assert data["coupon_released"] is True

    session = _db(engine)
    try:
        assert session.query(Order).filter(Order.id == order["id"]).first().status == "已取消"
        assert session.query(Product).filter(Product.id == product_id).first().stock == 10
        coupon = session.query(Coupon).filter(Coupon.id == coupon_id).first()
        assert coupon.status == "unused" and coupon.order_id is None
        action = session.query(PendingAction).filter(
            PendingAction.token == proposal["token"]
        ).first()
        assert action.status == "confirmed" and action.used_at is not None
        assert action.result_json
        # 审计：actor / action / target / before / after 都在
        log = session.query(ActionAuditLog).one()
        assert log.user_id == _user_id(engine, "buyer")
        assert log.action_type == "cancel_order"
        assert log.target_type == "order"
        assert log.target_id == order["order_no"]
        assert json.loads(log.before_json)["status"] == "待付款"
        assert json.loads(log.after_json)["status"] == "已取消"
        assert log.result == "success"
    finally:
        session.close()


def test_confirm_is_idempotent(client, buyer_token, product_id, address_id, engine):
    from app.models.aftersale import ActionAuditLog
    from app.models.product import Product

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    first = _confirm(client, buyer_token, proposal["token"])
    second = _confirm(client, buyer_token, proposal["token"])
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["replayed"] is False
    assert second.json()["data"]["replayed"] is True
    assert second.json()["data"]["message"] == first.json()["data"]["message"]

    session = _db(engine)
    try:
        # 库存只回补一次（10，而不是 12），审计也只有一条
        assert session.query(Product).filter(Product.id == product_id).first().stock == 10
        assert session.query(ActionAuditLog).count() == 1
    finally:
        session.close()


def test_confirm_writes_trace_id(client, buyer_token, product_id, address_id, engine):
    from app.models.aftersale import ActionAuditLog

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])
    headers = {**buyer_token, "X-Request-ID": "trace-aftersale-001"}
    resp = _confirm(client, headers, proposal["token"])
    assert resp.status_code == 200

    session = _db(engine)
    try:
        log = session.query(ActionAuditLog).one()
        assert log.trace_id == "trace-aftersale-001"
    finally:
        session.close()


def test_confirm_expired_token_rejected(client, buyer_token, product_id, address_id, engine):
    from app.models.aftersale import PendingAction
    from app.models.order import Order

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    session = _db(engine)
    try:
        action = session.query(PendingAction).filter(
            PendingAction.token == proposal["token"]
        ).first()
        action.expires_at = datetime.now() - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    resp = _confirm(client, buyer_token, proposal["token"])
    assert resp.status_code == 400
    assert "过期" in resp.json()["message"]

    session = _db(engine)
    try:
        assert session.query(Order).filter(Order.id == order["id"]).first().status == "待付款"
    finally:
        session.close()


def test_confirm_rejects_other_user(client, buyer_token, buyer2_token,
                                    product_id, address_id, engine):
    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    # 换人确认 → 404（不泄露 token 是否存在）
    resp = _confirm(client, buyer2_token, proposal["token"])
    assert resp.status_code == 404
    # 换会话确认 → 400
    resp = _confirm(client, buyer_token, proposal["token"], session_id=999)
    assert resp.status_code == 400


def test_confirm_rejects_tampered_params(client, buyer_token, product_id,
                                         address_id, engine):
    from app.models.aftersale import PendingAction

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    session = _db(engine)
    try:
        action = session.query(PendingAction).filter(
            PendingAction.token == proposal["token"]
        ).first()
        action.params_json = json.dumps({"order_no": "ZG-TAMPERED-001"})
        session.commit()
    finally:
        session.close()

    resp = _confirm(client, buyer_token, proposal["token"])
    assert resp.status_code == 400
    assert "参数" in resp.json()["message"]


def test_cancel_proposal_changes_nothing(client, buyer_token, product_id,
                                         address_id, engine):
    from app.models.order import Order

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    resp = client.post(
        f"{BASE}/aftersale/actions/{proposal['token']}/cancel",
        headers=buyer_token, json={"session_id": 1},
    )
    assert resp.status_code == 200
    # 已取消的提案不能再确认
    assert _confirm(client, buyer_token, proposal["token"]).status_code == 400

    session = _db(engine)
    try:
        assert session.query(Order).filter(Order.id == order["id"]).first().status == "待付款"
    finally:
        session.close()


def test_compensation_task_when_stock_restore_fails(client, buyer_token, product_id,
                                                    address_id, engine, monkeypatch):
    """库存回补异常：订单仍取消成功，但落补偿任务并记 partial 审计"""
    from app.models.aftersale import ActionAuditLog, CompensationTask
    from app.models.order import Order
    from app.services import product_service

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    def _boom(db, product, delta):
        raise RuntimeError("模拟库存服务异常")

    monkeypatch.setattr(product_service, "adjust_stock", _boom)

    resp = _confirm(client, buyer_token, proposal["token"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stock_restored"] is False
    assert data["warnings"]

    session = _db(engine)
    try:
        assert session.query(Order).filter(Order.id == order["id"]).first().status == "已取消"
        task = session.query(CompensationTask).one()
        assert task.task_type == "restore_stock"
        assert task.status == "待补偿"
        log = session.query(ActionAuditLog).one()
        assert log.result == "partial"
    finally:
        session.close()


# ===== 退款工单 =====

def test_refund_ticket_created_for_paid_order(client, buyer_token, product_id,
                                              address_id, engine):
    from app.models.aftersale import AfterSalesTicket

    order = _create_order(client, buyer_token, product_id, address_id, pay=True)
    proposal = _propose(
        engine, "buyer", order["order_no"], "create_refund_ticket",
        {"order_no": order["order_no"], "reason": "尺码不合适"},
    )
    assert proposal["title"] == "申请退款"
    resp = _confirm(client, buyer_token, proposal["token"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["ticket_no"].startswith("RF")
    assert data["status"] == "待商家处理"
    assert data["amount"] == 200.0

    session = _db(engine)
    try:
        ticket = session.query(AfterSalesTicket).one()
        assert ticket.order_no == order["order_no"]
        assert ticket.reason == "尺码不合适"
    finally:
        session.close()

    # 同一订单重复申请：提议阶段就被拒绝
    from app.core.errors import BadRequestError
    from app.services import aftersale_service
    session = _db(engine)
    try:
        with pytest.raises(BadRequestError):
            aftersale_service.propose(
                session, _user_id(engine, "buyer"), 1, "create_refund_ticket",
                {"order_no": order["order_no"], "reason": "再申请一次"},
            )
    finally:
        session.close()


def test_refund_rejected_for_unpaid_order(client, buyer_token, product_id,
                                          address_id, engine):
    from app.core.errors import BadRequestError
    from app.services import aftersale_service

    order = _create_order(client, buyer_token, product_id, address_id)
    session = _db(engine)
    try:
        with pytest.raises(BadRequestError) as exc:
            aftersale_service.propose(
                session, _user_id(engine, "buyer"), 1, "create_refund_ticket",
                {"order_no": order["order_no"], "reason": "不想要了"},
            )
        assert "取消订单" in exc.value.message
    finally:
        session.close()


# ===== 修改收货地址 =====

def test_change_address_updates_snapshot(client, buyer_token, product_id,
                                         address_id, engine):
    from app.models.order import Order

    new_address = client.post(f"{BASE}/addresses", headers=buyer_token, json={
        "receiver": "韩梅梅", "phone": "13900139000",
        "region": "上海市 浦东新区", "detail": "世纪大道 100 号",
    }).json()["data"]
    order = _create_order(client, buyer_token, product_id, address_id)

    proposal = _propose(
        engine, "buyer", order["order_no"], "change_address",
        {"order_no": order["order_no"], "address_id": new_address["id"]},
    )
    assert "韩梅梅" in proposal["summary"]
    resp = _confirm(client, buyer_token, proposal["token"])
    assert resp.status_code == 200, resp.text

    session = _db(engine)
    try:
        updated = session.query(Order).filter(Order.id == order["id"]).first()
        assert updated.receiver_name == "韩梅梅"
        assert updated.receiver_phone == "13900139000"
        assert "世纪大道 100 号" in updated.receiver_address
    finally:
        session.close()


def test_change_address_rejected_after_shipping(client, buyer_token, product_id,
                                                address_id, engine):
    from app.core.errors import BadRequestError
    from app.models.order import Order
    from app.services import aftersale_service

    order = _create_order(client, buyer_token, product_id, address_id, pay=True)
    session = _db(engine)
    try:
        db_order = session.query(Order).filter(Order.id == order["id"]).first()
        db_order.status = "已发货"
        session.commit()

        with pytest.raises(BadRequestError) as exc:
            aftersale_service.propose(
                session, _user_id(engine, "buyer"), 1, "change_address",
                {"order_no": order["order_no"], "address_id": address_id},
            )
        assert "发货后不可修改" in exc.value.message
    finally:
        session.close()


def test_change_address_rejects_foreign_address(client, buyer_token, buyer2_token,
                                                product_id, address_id, engine):
    from app.core.errors import NotFoundError
    from app.services import aftersale_service

    # buyer2 的地址
    foreign = client.post(f"{BASE}/addresses", headers=buyer2_token, json={
        "receiver": "张三", "phone": "13700137000",
        "region": "广州市 天河区", "detail": "体育西路 1 号",
    }).json()["data"]
    order = _create_order(client, buyer_token, product_id, address_id)

    session = _db(engine)
    try:
        with pytest.raises(NotFoundError):
            aftersale_service.propose(
                session, _user_id(engine, "buyer"), 1, "change_address",
                {"order_no": order["order_no"], "address_id": foreign["id"]},
            )
    finally:
        session.close()


# ===== 鉴权 =====

def test_confirm_requires_login(client, buyer_token, product_id, address_id, engine):
    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])
    resp = client.post(
        f"{BASE}/aftersale/actions/{proposal['token']}/confirm",
        json={"session_id": 1},
    )
    assert resp.status_code == 401


# ===== 并发前置修复：条件更新 =====

def test_stock_deduction_is_conditional(engine, product_id):
    """库存扣减用条件更新：不足时影响行数 0，库存不变；成功后再次超扣也失败"""
    from app.models.product import Product
    from app.services import product_service

    session = _db(engine)
    try:
        assert product_service.deduct_stock(session, product_id, 11) is False
        session.rollback()
        assert session.get(Product, product_id).stock == 10

        assert product_service.deduct_stock(session, product_id, 4) is True
        session.commit()
        assert session.get(Product, product_id).stock == 6

        assert product_service.deduct_stock(session, product_id, 7) is False
        session.rollback()
        assert session.get(Product, product_id).stock == 6
    finally:
        session.close()


def test_coupon_redeem_is_conditional(client, buyer_token, engine):
    """同一张券第二次核销必须失败（状态条件更新，而不是先查后改）"""
    from app.core.errors import BadRequestError
    from app.models.coupon import Coupon
    from app.services import coupon_service

    resp = client.post(f"{BASE}/coupons/claim", headers=buyer_token, json={"threshold": 199})
    coupon_id = resp.json()["data"]["id"]

    session = _db(engine)
    try:
        user_id = _user_id(engine, "buyer")
        discount, coupon = coupon_service.redeem(session, user_id, coupon_id, 300)
        assert discount == 30
        assert coupon.status == "used"

        with pytest.raises(BadRequestError) as exc:
            coupon_service.redeem(session, user_id, coupon_id, 300)
        assert "已被使用" in exc.value.message
        assert session.get(Coupon, coupon_id).status == "used"
    finally:
        session.close()


# ===== 工具异常隔离 =====

def test_execute_tool_isolates_unexpected_exception(client, buyer_token, engine, monkeypatch):
    """单个工具崩溃不应拖垮整轮问答：异常被兜住并转成可读话术"""
    from app.services import tools

    def _boom(*args, **kwargs):
        raise RuntimeError("模拟工具崩溃")

    monkeypatch.setitem(tools._HANDLERS, "query_my_orders", _boom)
    session = _db(engine)
    try:
        result = tools.execute_tool(
            "query_my_orders", {}, session, None, _user_id(engine, "buyer")
        )
        assert result.payload is None
        assert "暂时不可用" in result.text
    finally:
        session.close()


def test_execute_tool_turns_business_error_into_text(client, buyer_token, engine, monkeypatch):
    """业务异常（AppError）转成模型可转述的话术，而不是 500"""
    from app.core.errors import BadRequestError
    from app.services import tools

    def _bad(*args, **kwargs):
        raise BadRequestError("订单状态不允许")

    monkeypatch.setitem(tools._HANDLERS, "query_my_orders", _bad)
    session = _db(engine)
    try:
        result = tools.execute_tool(
            "query_my_orders", {}, session, None, _user_id(engine, "buyer")
        )
        assert "订单状态不允许" in result.text
    finally:
        session.close()


# ===== 商家审核 =====

@pytest.fixture
def merchant_token(client, make_user):
    make_user("shopadmin", "shopadmin123", "admin")
    return _login(client, "shopadmin", "shopadmin123")


def _create_refund_ticket(client, token, product_id, address_id, engine,
                          reason="尺码不合适"):
    """下单 → 支付 → 提议退款 → 确认，返回 (订单, 工单数据)"""
    order = _create_order(client, token, product_id, address_id, pay=True)
    proposal = _propose(
        engine, "buyer", order["order_no"], "create_refund_ticket",
        {"order_no": order["order_no"], "reason": reason},
    )
    resp = _confirm(client, token, proposal["token"])
    assert resp.status_code == 200, resp.text
    return order, resp.json()["data"]


def test_merchant_lists_and_approves_ticket(client, buyer_token, merchant_token,
                                            product_id, address_id, engine):
    from app.models.aftersale import ActionAuditLog, AfterSalesTicket

    _, ticket = _create_refund_ticket(client, buyer_token, product_id, address_id, engine)

    resp = client.get(f"{BASE}/merchant/aftersale/tickets", headers=merchant_token)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 1
    assert items[0]["ticket_no"] == ticket["ticket_no"]
    assert items[0]["status"] == "待商家处理"
    ticket_id = items[0]["id"]

    resp = client.post(
        f"{BASE}/merchant/aftersale/tickets/{ticket_id}/approve", headers=merchant_token
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "已完成"

    # 重复审核：条件更新的影响行数为 0 → 400
    resp = client.post(
        f"{BASE}/merchant/aftersale/tickets/{ticket_id}/approve", headers=merchant_token
    )
    assert resp.status_code == 400

    session = _db(engine)
    try:
        assert session.get(AfterSalesTicket, ticket_id).status == "已完成"
        log = session.query(ActionAuditLog).filter(
            ActionAuditLog.action_type == "review_after_sales_ticket"
        ).one()
        assert log.target_type == "after_sales_ticket"
        assert log.result == "success"
        assert json.loads(log.before_json)["status"] == "待商家处理"
        assert json.loads(log.after_json)["status"] == "已完成"
    finally:
        session.close()


def test_merchant_can_reject_ticket(client, buyer_token, merchant_token,
                                    product_id, address_id, engine):
    from app.models.aftersale import AfterSalesTicket

    _, ticket = _create_refund_ticket(client, buyer_token, product_id, address_id, engine)
    items = client.get(
        f"{BASE}/merchant/aftersale/tickets", headers=merchant_token
    ).json()["data"]
    ticket_id = items[0]["id"]

    resp = client.post(
        f"{BASE}/merchant/aftersale/tickets/{ticket_id}/reject", headers=merchant_token
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "已驳回"

    session = _db(engine)
    try:
        assert session.get(AfterSalesTicket, ticket_id).status == "已驳回"
    finally:
        session.close()


def test_merchant_aftersale_requires_merchant_role(client, buyer_token,
                                                   product_id, address_id, engine):
    """顾客访问商家审核接口 → 403"""
    _create_refund_ticket(client, buyer_token, product_id, address_id, engine)
    resp = client.get(f"{BASE}/merchant/aftersale/tickets", headers=buyer_token)
    assert resp.status_code == 403
    resp = client.post(
        f"{BASE}/merchant/aftersale/tickets/1/approve", headers=buyer_token
    )
    assert resp.status_code == 403


def test_other_merchant_cannot_see_or_review_ticket(client, buyer_token, product_id,
                                                    address_id, engine, make_user):
    """其他商家既看不到工单，也不能审核（统一 404，不泄露存在性）"""
    from app.repositories.tenant_repository import TenantRepository

    session = _db(engine)
    try:
        other = TenantRepository(session).create(code="othershop", name="其他商家")
        other_id = other.id
    finally:
        session.close()
    make_user("othershop", "othershop123", "admin", tenant_id=other_id)
    other_token = _login(client, "othershop", "othershop123")

    _create_refund_ticket(client, buyer_token, product_id, address_id, engine)
    resp = client.get(f"{BASE}/merchant/aftersale/tickets", headers=other_token)
    assert resp.status_code == 200
    assert resp.json()["data"] == []

    ticket_id = client.get(f"{BASE}/aftersale/tickets", headers=buyer_token).json()["data"][0]["id"]
    resp = client.post(
        f"{BASE}/merchant/aftersale/tickets/{ticket_id}/approve", headers=other_token
    )
    assert resp.status_code == 404


# ===== 重复确认与并发闸门 =====

def test_refund_confirmed_twenty_times_creates_one_ticket(client, buyer_token,
                                                          product_id, address_id, engine):
    """20 次重复确认：第一次建单，其余全部回放，工单与审计都只有一条"""
    from app.models.aftersale import ActionAuditLog, AfterSalesTicket

    order = _create_order(client, buyer_token, product_id, address_id, pay=True)
    proposal = _propose(
        engine, "buyer", order["order_no"], "create_refund_ticket",
        {"order_no": order["order_no"], "reason": "不想要了"},
    )

    results = [_confirm(client, buyer_token, proposal["token"]) for _ in range(20)]
    assert all(r.status_code == 200 for r in results)
    assert results[0].json()["data"]["replayed"] is False
    assert all(r.json()["data"]["replayed"] is True for r in results[1:])

    session = _db(engine)
    try:
        assert session.query(AfterSalesTicket).count() == 1
        logs = session.query(ActionAuditLog).filter(
            ActionAuditLog.action_type == "create_refund_ticket"
        ).all()
        assert len(logs) == 1
    finally:
        session.close()


def test_claim_gate_only_one_execution(client, buyer_token, product_id,
                                       address_id, engine):
    """并发闸门单测：used_at 条件更新第一次返回 1，第二次返回 0"""
    from app.repositories.aftersale_repository import AfterSaleRepository

    order = _create_order(client, buyer_token, product_id, address_id)
    proposal = _propose(engine, "buyer", order["order_no"])

    session = _db(engine)
    try:
        repo = AfterSaleRepository(session)
        action = repo.get_by_token(proposal["token"])
        assert repo.claim(action.id, None) == 1
        assert repo.claim(action.id, None) == 0
    finally:
        session.close()

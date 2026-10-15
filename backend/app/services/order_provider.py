"""订单查询提供方（OrderProvider）

把「订单数据从哪来」和「Agent 怎么用订单结果」解耦：

- local   ：查本地 SQLite 的 orders 表（演示数据，默认）
- openapi ：调用第三方电商平台 OpenAPI，查真实订单

由 .env 的 ORDER_PROVIDER 切换，tools.py 无需改动。
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings

LOCAL_PROVIDER = "local"
OPENAPI_PROVIDER = "openapi"


class OrderServiceError(Exception):
    """订单服务不可用：未配置、网络异常、鉴权失败、平台返回错误等"""


@dataclass
class OrderInfo:
    """订单的统一内部结构，屏蔽各平台的字段差异"""

    order_no: str
    product_name: str = ""
    amount: float = 0.0
    status: str = ""
    logistics: str = ""


class OrderProvider:
    """订单查询接口：查到返回 OrderInfo，查不到返回 None，服务异常抛 OrderServiceError"""

    def query(self, order_no: str, tenant_id: int | None = None) -> OrderInfo | None:
        raise NotImplementedError


class LocalDbOrderProvider(OrderProvider):
    """本地订单表（演示用，数据由 main.py 启动时写入，按租户隔离）"""

    def __init__(self, db: Session):
        self.db = db

    def query(self, order_no: str, tenant_id: int | None = None) -> OrderInfo | None:
        from app.repositories.order_repository import OrderRepository

        order = OrderRepository(self.db).get_by_order_no(order_no, tenant_id)
        if not order:
            return None
        return OrderInfo(
            order_no=order.order_no,
            product_name=order.product_name,
            amount=order.amount,
            status=order.status,
            logistics=order.logistics,
        )


class OpenApiOrderProvider(OrderProvider):
    """第三方电商平台 OpenAPI（通用 REST 约定）

    请求：GET {ORDER_API_BASE_URL}{ORDER_API_ORDER_PATH}，订单号作为路径参数，
          同时以查询参数带 order_no 与 access_token
    鉴权：请求头 X-App-Key 带 app_key，查询参数 access_token 带令牌
    响应：{"code": 0, "message": "ok", "data": {订单字段}}（code 为 0 视为成功）

    适配真实平台时只需改两处：
    1. 若平台要求签名（MD5/HMAC），在 _build_params 里补上；
    2. 若平台字段名不同，在 _to_order_info 里改映射。
    """

    def __init__(self):
        self.base_url = (settings.order_api_base_url or "").rstrip("/")
        self.order_path = settings.order_api_order_path
        self.timeout = settings.order_api_timeout

    def query(self, order_no: str, tenant_id: int | None = None) -> OrderInfo | None:
        # 第三方平台自行按其鉴权/店铺维度隔离，这里忽略 tenant_id
        if not self.base_url:
            raise OrderServiceError("订单查询服务未配置（缺少 ORDER_API_BASE_URL）")

        url = self.base_url + self.order_path.format(order_no=order_no)
        try:
            resp = httpx.get(
                url,
                params=self._build_params(order_no),
                headers=self._build_headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as exc:
            raise OrderServiceError(f"订单查询服务请求失败：{exc}") from exc
        except ValueError as exc:
            raise OrderServiceError("订单查询服务返回了非 JSON 内容") from exc

        if not isinstance(payload, dict):
            raise OrderServiceError("订单查询服务响应格式异常")

        if payload.get("code") != 0:
            raise OrderServiceError(
                f"订单查询服务返回错误：{payload.get('message') or payload.get('code')}"
            )

        data = payload.get("data")
        if not data:
            return None
        return self._to_order_info(data)

    def _build_params(self, order_no: str) -> dict:
        params = {"order_no": order_no}
        if settings.order_access_token:
            params["access_token"] = settings.order_access_token
        return params

    def _build_headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if settings.order_app_key:
            headers["X-App-Key"] = settings.order_app_key
        return headers

    @staticmethod
    def _to_order_info(data: dict) -> OrderInfo:
        """平台字段 → 内部结构（换平台时只改这里）"""
        return OrderInfo(
            order_no=str(data.get("order_no") or ""),
            product_name=str(data.get("product_name") or ""),
            amount=float(data.get("amount") or 0),
            status=str(data.get("status") or ""),
            logistics=str(data.get("logistics") or ""),
        )


def get_provider(db: Session | None = None) -> OrderProvider:
    """按配置返回订单提供方"""
    name = (settings.order_provider or LOCAL_PROVIDER).strip().lower()
    if name == OPENAPI_PROVIDER:
        return OpenApiOrderProvider()
    if name == LOCAL_PROVIDER:
        return LocalDbOrderProvider(db)
    raise OrderServiceError(
        f"未知的 ORDER_PROVIDER 配置：{settings.order_provider}（可选 local / openapi）"
    )

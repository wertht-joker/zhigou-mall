"""数据模型包

这里显式导入全部模型，保证任何一次 `import app.models` 都会把表注册进
Base.metadata（Alembic autogenerate 与建表都依赖完整的 metadata）。
"""
from app.models.database import Base, SessionLocal, engine, get_db
from app.models.address import Address
from app.models.aftersale import (
    ActionAuditLog,
    AfterSalesTicket,
    CompensationTask,
    PendingAction,
)
from app.models.cart import CartItem
from app.models.category import Category
from app.models.coupon import Coupon
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.product import Product, ProductCategory, ProductVariant
from app.models.qa_event import QaEvent
from app.models.review import Review
from app.models.session import Message, Session
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "Address",
    "ActionAuditLog",
    "AfterSalesTicket",
    "CartItem",
    "Category",
    "CompensationTask",
    "Coupon",
    "Document",
    "Feedback",
    "Order",
    "OrderItem",
    "Payment",
    "PendingAction",
    "Product",
    "ProductCategory",
    "ProductVariant",
    "QaEvent",
    "Review",
    "Message",
    "Session",
    "Tenant",
    "User",
]

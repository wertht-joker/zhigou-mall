"""数据模型包

这里显式导入全部模型，保证任何一次 `import app.models` 都会把表注册进
Base.metadata（Alembic autogenerate 与建表都依赖完整的 metadata）。
"""
from app.models.database import Base, SessionLocal, engine, get_db
from app.models.category import Category
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.order import Order
from app.models.session import Message, Session
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "Category",
    "Document",
    "Feedback",
    "Order",
    "Message",
    "Session",
    "Tenant",
    "User",
]

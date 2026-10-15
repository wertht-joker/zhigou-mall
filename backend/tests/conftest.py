"""测试公共夹具：内存数据库、测试客户端、外部依赖打桩

设计目标：所有测试都不触碰真实 LLM / Milvus / BGE 模型与网络，
保证本地与 CI 都能稳定、快速地跑完，也不会污染开发用的 kb.db。

约定：
- engine：共享一份内存 SQLite（StaticPool），已建好全部表
- db：绑定该内存库的 Session，供服务层用例直接调用
- client：FastAPI TestClient，用内存库覆盖 get_db，并给 LLM 打桩
- make_user / admin_token / user_token：快速造登录态
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 导入 app 会连带把全部 models 注册到 Base.metadata，务必在建表之前完成
from app.main import app
from app.models.database import Base
from app.models.database import get_db as real_get_db

# 测试期间固定回答，避免依赖真实模型
STUB_ANSWER = "这是测试用的固定回答。"


@pytest.fixture
def engine():
    """一份被多线程共享的内存 SQLite（StaticPool 保证连接复用）"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """绑定内存库的会话"""
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _stub_llm(monkeypatch):
    """把 DeepSeek 调用替换为固定回答，测试不联网"""
    from app.rag import generator

    monkeypatch.setattr(
        generator,
        "chat_with_tools",
        lambda messages, tools: {"role": "assistant", "content": STUB_ANSWER},
    )
    monkeypatch.setattr(generator, "generate_text", lambda messages: STUB_ANSWER)
    monkeypatch.setattr(
        generator,
        "stream_answer",
        lambda messages: iter([STUB_ANSWER]),
    )


@pytest.fixture
def client(engine, monkeypatch):
    """TestClient：内存库覆盖 get_db，启动钩子与 LLM 全部打桩"""
    # 启动钩子会迁移并写真实库，这里禁用，改为完全依赖内存库
    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr("app.main.create_default_admin", lambda: None)
    monkeypatch.setattr("app.main.seed_demo_orders", lambda: None)
    # 清空进程内限流桶，避免用例间相互影响
    from app.core.rate_limit import reset_memory_buckets

    reset_memory_buckets()
    _stub_llm(monkeypatch)

    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[real_get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(engine):
    """在内存库里直接造一个用户，返回 (id, username, role)

    tenant_id 默认归入默认租户（与登录时的租户解析一致）；
    也可显式传 tenant_id 造出归属指定租户的用户。
    """
    from app.models.user import User
    from app.services import tenant_service
    from app.utils import security

    Session = sessionmaker(bind=engine)

    def _make(username: str = "admin", password: str = "admin123", role: str = "admin",
              tenant_id: int | None = None):
        session = Session()
        if tenant_id is None:
            tenant_id = tenant_service.ensure_default_tenant(session).id
        user = User(
            username=username,
            password_hash=security.hash_password(password),
            role=role,
            tenant_id=tenant_id,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        result = (user.id, user.username, user.role)
        session.close()
        return result

    return _make


def _login(client, username: str, password: str, tenant_code: str | None = None) -> str:
    payload = {"username": username, "password": password}
    if tenant_code:
        payload["tenant_code"] = tenant_code
    resp = client.post("/api/v1/auth/login", json=payload)
    return resp.json()["data"]["token"]


@pytest.fixture
def admin_token(client, make_user):
    """管理员登录态，返回请求头"""
    make_user("admin", "admin123", "admin")
    return {"Authorization": "Bearer " + _login(client, "admin", "admin123")}


@pytest.fixture
def user_token(client, make_user):
    """普通用户登录态，返回请求头"""
    make_user("alice", "alice123", "user")
    return {"Authorization": "Bearer " + _login(client, "alice", "alice123")}

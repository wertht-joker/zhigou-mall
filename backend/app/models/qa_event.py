"""AI 问答事件（知识缺口闭环的数据底座）

每次客服回答后落一条事件，记录问题、答案、检索证据数量、充分性、
忠实度与用户反馈。平台侧据此聚类出「知识缺口」，生成 FAQ 草稿并入库。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class QaEvent(Base):
    __tablename__ = "qa_events"
    __table_args__ = (
        Index("ix_qa_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_qa_events_message", "message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 对应 assistant 消息 ID，用于反馈（点赞/点踩）回填
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 本轮检索到的证据条数；0 表示知识库没有召回
    sources_count: Mapped[int] = mapped_column(Integer, default=0)
    # sufficient / partial / insufficient
    sufficiency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 0~1，仅知识库类回答有值
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 本次检索链路：none / vector / hybrid / hybrid+rerank
    route: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # up / down
    feedback: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # 已生成 FAQ 并入库后置为 True，缺口看板不再展示
    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 该坏例由哪篇 FAQ 文档解决，用于发布后的命中率回归
    resolved_doc_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

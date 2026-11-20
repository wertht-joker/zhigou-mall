"""可信回答守卫（方向 B）测试：claim 分解 / 支撑判定 / 充分性门控 / SSE verify

全部使用规则校验与打桩检索，不依赖 LLM / Milvus / BGE，保证离线可复现。
"""
import json

import httpx
from openai import APIConnectionError

from app.rag import generator, retriever, sufficiency, verifier
from app.services import chat_service, tools

SOURCES = [
    {
        "doc_id": 1,
        "chunk_index": 0,
        "doc_name": "售后政策.md",
        "text": "商品签收后7天内可以申请无理由退货，退货运费由买家承担。",
        "score": 0.9,
    },
    {
        "doc_id": 2,
        "chunk_index": 0,
        "doc_name": "退款说明.md",
        "text": "退款将在审核通过后7个工作日内原路退回。",
        "score": 0.8,
    },
]


def _make_doc(db, name: str = "售后政策.md"):
    """建一条文档元数据，供检索工具补全 doc_name"""
    from app.models.document import Document

    doc = Document(
        name=name, type="md", size=0, chunk_count=2, status="done", tenant_id=None
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _hits(doc_id: int) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "chunk_index": 0,
            "text": "商品签收后7天内可以申请无理由退货，退货运费由买家承担。",
            "score": 0.91,
        },
        {
            "doc_id": doc_id,
            "chunk_index": 1,
            "text": "退款将在审核通过后7个工作日内原路退回。",
            "score": 0.86,
        },
    ]


def _patch_search(monkeypatch, hits: list[dict]) -> None:
    """检索工具已改用 search_with_meta，测试统一打桩这个入口"""
    def _fake(*args, **kwargs):
        return hits, {
            "strategy": "auto",
            "cache": "miss",
            "elapsed_ms": 0.0,
            "hits": len(hits),
        }

    monkeypatch.setattr(retriever, "search_with_meta", _fake)


def _parse_sse(chunks) -> list[dict]:
    events = []
    for chunk in chunks:
        line = chunk.strip()
        if not line.startswith("data:"):
            continue
        events.append(json.loads(line[5:].strip()))
    return events


# ===== claim 分解 =====

def test_decompose_claims_splits_sentences_and_limits():
    answer = "签收后7天内可以申请退货。退款将在7个工作日内原路退回！感谢您的咨询。"
    claims = verifier.decompose_claims(answer, max_claims=2)
    assert len(claims) == 2
    assert "签收" in claims[0]
    assert "退款" in claims[1]


def test_decompose_claims_skips_closing_offers():
    assert verifier.decompose_claims("需要我帮您查一下具体订单吗？") == []
    assert verifier.decompose_claims("如需准确答复，可转人工客服核实。") == []


def test_decompose_claims_skips_headings():
    answer = "退款到账时间分两段来看：\n商家处理：3 个工作日内退款至原支付账户。"
    claims = verifier.decompose_claims(answer)
    assert len(claims) == 1
    assert "商家处理" in claims[0]


def test_decompose_claims_skips_smalltalk_and_refusal():
    assert verifier.decompose_claims("您好！请问有什么可以帮您？") == []
    assert verifier.decompose_claims("未找到相关答案，建议联系人工客服。") == []
    # 较长的拒答句同样不算事实性 claim，否则「忠实度」会被拒答话术拉低
    assert verifier.decompose_claims(
        "抱歉，知识库暂时查询不到结果，我这边无法确认退款到账的具体时效，"
        "请稍后再试或联系人工客服核实。如果您方便，也可以告诉我具体订单号。"
    ) == []


# ===== claim 级支撑判定 =====

def test_verify_claim_supported_by_evidence():
    result = verifier.verify_claim("商品签收后7天内可以申请无理由退货", SOURCES)
    assert result["verdict"] == "supported"
    assert result["confidence"] >= 0.6
    assert result["source"]["doc_id"] == 1


def test_verify_claim_unsupported_without_evidence():
    result = verifier.verify_claim("会员每月可领取一张无门槛优惠券", SOURCES)
    assert result["verdict"] == "unsupported"
    assert result["confidence"] < 0.35


def test_verify_answer_aggregates_and_marks_sources():
    answer = (
        "商品签收后7天内可以申请无理由退货。"
        "退款将在审核通过后7个工作日内原路退回。"
        "会员每月可领取一张无门槛优惠券。"
    )
    report = verifier.verify_answer(answer, SOURCES, max_claims=8, threshold=0.8)

    assert report["total"] == 3
    assert report["supported"] == 2
    assert report["unsupported"] == 1
    assert report["faithfulness"] < 0.8
    assert report["hallucination_rate"] > 0
    assert report["low_confidence"] is True

    verdicts = {f"{s['doc_id']}:{s['chunk_index']}": s["verdict"] for s in report["sources"]}
    assert verdicts["1:0"] == "supported"
    assert verdicts["2:0"] == "supported"


def test_verify_answer_high_confidence_not_flagged():
    answer = "商品签收后7天内可以申请无理由退货。退款将在审核通过后7个工作日内原路退回。"
    report = verifier.verify_answer(answer, SOURCES, threshold=0.8)

    assert report["total"] == 2
    assert report["supported"] == 2
    assert report["faithfulness"] == 1.0
    assert report["low_confidence"] is False


def test_should_refuse_on_empty_evidence_or_insufficient_gate():
    assert verifier.should_refuse([], {"level": "insufficient"}) is True
    assert verifier.should_refuse([], {"level": "sufficient"}) is True
    assert verifier.should_refuse(SOURCES, {"level": "insufficient"}) is True
    assert verifier.should_refuse(SOURCES, {"level": "sufficient"}) is False


# ===== 证据充分性门控 =====

def test_sufficiency_levels():
    relevant = sufficiency.judge_sufficiency("签收后可以退货吗", SOURCES)
    assert relevant["level"] == "sufficient"
    assert relevant["score"] >= relevant["threshold"]

    irrelevant = sufficiency.judge_sufficiency(
        "发票怎么开",
        [{"text": "会员积分：消费一元累计一积分。", "score": 0.9}],
    )
    assert irrelevant["level"] == "insufficient"

    empty = sufficiency.judge_sufficiency("退货政策", [])
    assert empty["level"] == "insufficient"
    assert empty["hit_count"] == 0


# ===== 检索工具集成 =====

def test_search_tool_returns_sufficiency_meta(db, monkeypatch):
    doc = _make_doc(db)
    _patch_search(monkeypatch, _hits(doc.id))

    result = tools.execute_tool(
        "search_knowledge_base", {"query": "签收后可以退货吗"}, db
    )

    assert result.meta["kb_used"] is True
    assert result.meta["sufficiency"]["level"] == "sufficient"
    assert len(result.sources) == 2
    assert result.sources[0]["doc_name"] == "售后政策.md"


def test_search_tool_marks_insufficient_when_empty(db, monkeypatch):
    _patch_search(monkeypatch, [])

    result = tools.execute_tool(
        "search_knowledge_base", {"query": "发票怎么开"}, db
    )

    assert result.meta["kb_used"] is True
    assert result.meta["sufficiency"]["level"] == "insufficient"
    assert "人工客服" in result.text
    assert result.sources == []


# ===== SSE / 非流式接口集成 =====

def _stub_agent(monkeypatch, answer: str, query: str = "签收后可以退货吗"):
    """让 Agent 第一轮调用知识库工具，第二轮结束，再流式给出固定答案"""
    from app.rag import generator

    calls = {"n": 0}

    def fake_chat_with_tools(messages, tool_defs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "arguments": json.dumps({"query": query}, ensure_ascii=False),
                    },
                }],
            }
        return {"role": "assistant", "content": ""}

    monkeypatch.setattr(generator, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(generator, "stream_answer", lambda messages: iter([answer]))
    monkeypatch.setattr(generator, "generate_text", lambda messages: answer)


def test_chat_stream_emits_verify_event(db, monkeypatch):
    doc = _make_doc(db)
    _patch_search(monkeypatch, _hits(doc.id))
    answer = "商品签收后7天内可以申请无理由退货。退款将在审核通过后7个工作日内原路退回。"
    _stub_agent(monkeypatch, answer)

    events = _parse_sse(chat_service.ask_stream(db, "签收后可以退货吗"))
    types = [event["type"] for event in events]

    assert "meta" in types
    assert "verify" in types
    assert types[-1] == "done"
    assert types.index("verify") < types.index("done")

    verify = next(event for event in events if event["type"] == "verify")
    assert verify["total"] == 2
    assert verify["supported"] == 2
    assert verify["low_confidence"] is False
    assert verify["refuse"] is False
    assert {s["verdict"] for s in verify["sources"]} == {"supported"}
    assert verify["sufficiency"]["level"] in {"sufficient", "partial"}
    assert "忠实度" in verify["message"]


def test_chat_stream_marks_low_confidence_answer(db, monkeypatch):
    doc = _make_doc(db)
    _patch_search(monkeypatch, _hits(doc.id))
    _stub_agent(monkeypatch, "会员每月可领取一张无门槛优惠券。")

    events = _parse_sse(chat_service.ask_stream(db, "签收后可以退货吗"))
    verify = next(event for event in events if event["type"] == "verify")

    assert verify["unsupported"] == 1
    assert verify["low_confidence"] is True
    assert verify["refuse"] is False  # 有证据但个别句子无依据 → 提示而非直接拒答
    assert "未在知识库中找到直接依据" in verify["message"]


def test_chat_stream_flags_insufficient_when_search_fails(db, monkeypatch):
    """检索工具异常时也要给出「证据不足」结论，而不是静默跳过校验"""
    def _boom(*args, **kwargs):
        raise RuntimeError("milvus down")

    monkeypatch.setattr(retriever, "search_with_meta", _boom)
    _stub_agent(monkeypatch, "退款一般会在 7 个工作日内到账。")

    events = _parse_sse(chat_service.ask_stream(db, "退货退款多久到账"))
    verify = next(event for event in events if event["type"] == "verify")

    assert verify["sources"] == []
    assert verify["sufficiency"]["level"] == "insufficient"
    assert verify["refuse"] is True
    assert verify["low_confidence"] is True


def test_chat_non_stream_includes_verification(db, monkeypatch):
    doc = _make_doc(db)
    _patch_search(monkeypatch, _hits(doc.id))
    _stub_agent(monkeypatch, "商品签收后7天内可以申请无理由退货。")

    response = chat_service.ask(db, "签收后可以退货吗")

    assert response.verification is not None
    assert response.verification["total"] == 1
    assert response.sources[0].verdict in {"supported", "partial"}
    assert response.sources[0].confidence >= 0.6


def test_faithfulness_eval_smoke():
    """可信回答评测脚本可离线跑通，指标处于合理区间"""
    from evals.faithfulness_eval import evaluate

    report = evaluate()
    assert report["cases"] >= 60
    assert report["answerable"] >= 40
    assert report["unanswerable"] >= 15
    assert 0.0 <= report["faithfulness"] <= 1.0
    assert report["citation_precision"] >= 0.8
    assert report["adversarial_detection_rate"] >= 0.5
    assert report["p95_latency_ms"] < 1500


def test_chat_skips_verification_without_knowledge_base(db, monkeypatch):
    """纯闲聊没查知识库，不应把回答当成「有待校验的引用结论」"""
    from app.rag import generator

    monkeypatch.setattr(
        generator,
        "chat_with_tools",
        lambda messages, tool_defs: {"role": "assistant", "content": "您好，我是 AI 客服。"},
    )
    response = chat_service.ask(db, "你好")

    assert response.verification is None


# ===== 模型不可用时的本地降级 =====

def _stub_llm_down(monkeypatch):
    def _boom(*args, **kwargs):
        raise APIConnectionError(
            request=httpx.Request(
                "POST", "https://api.deepseek.com/chat/completions"
            )
        )

    monkeypatch.setattr(generator, "chat_with_tools", _boom)


def test_chat_ask_falls_back_to_kb_when_llm_unavailable(db, monkeypatch):
    """DeepSeek 连不上时返回知识库摘录，而不是整条问答 500"""
    doc = _make_doc(db)
    _patch_search(monkeypatch, _hits(doc.id))
    _stub_llm_down(monkeypatch)

    response = chat_service.ask(db, "签收后可以退货吗")

    assert "AI 服务暂时不可用" in response.answer
    assert "7天内" in response.answer
    assert response.sources
    assert response.sources[0].doc_name == "售后政策.md"


def test_chat_stream_falls_back_when_llm_unavailable(db, monkeypatch):
    """流式链路同样降级：先发 meta，再发摘录，最后正常 done"""
    doc = _make_doc(db)
    _patch_search(monkeypatch, _hits(doc.id))
    _stub_llm_down(monkeypatch)

    events = _parse_sse(chat_service.ask_stream(db, "签收后可以退货吗"))
    types = [event["type"] for event in events]
    delta = "".join(
        event["content"] for event in events if event["type"] == "delta"
    )

    assert "meta" in types
    assert "AI 服务暂时不可用" in delta
    assert "7天内" in delta
    assert types[-1] == "done"
    meta = next(event for event in events if event["type"] == "meta")
    assert meta["sources"]

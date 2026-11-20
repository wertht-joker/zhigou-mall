"""问答服务：Agent 自主决策（工具调用循环）+ 流式输出

与旧版的区别：旧版链路是写死的「改写 → 检索 → 生成」，
现在由大模型自主决定调用哪个工具、用什么参数、调几轮，再汇总回答。
"""
import json
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ServiceUnavailableError
from app.rag import generator, verifier
from app.schemas.chat import ChatResponse, Source
from app.services import qa_event_service, session_service, tools

AGENT_SYSTEM_PROMPT = """你是「智购商城」的 AI 智能客服助手，可以调用工具获取信息后再回答用户。

可用工具：
1. search_knowledge_base —— 检索平台知识库（售后政策、退换货流程、物流配送、支付方式、会员积分等）。
2. query_my_orders —— 查询当前顾客自己的订单状态、物流和商品明细。
3. recommend_products —— 商品导购，按用户需求推荐在售商品。
4. list_my_addresses —— 查询当前顾客的收货地址簿（含地址 ID）。
5. propose_after_sales_action —— 发起售后操作提案：取消待付款订单 / 申请退款 / 修改收货地址。

要求：
1. 涉及"规则/流程"类的问题（售后政策、退换货流程、物流配送规则、支付方式、会员积分、
   账号问题等），必须先调用 search_knowledge_base 获取资料，只根据检索到的内容回答，不要编造；
1.1 当用户问的是"我这单能不能退 / 这笔订单适用什么政策"时，先调用 query_my_orders
   拿到订单号，再调用 search_knowledge_base 并传入 order_no；系统会按订单成交时
   生效的政策版本检索，不要拿最新政策直接套历史订单；
2. 检索结果中没有答案时，明确回复"未找到相关答案"；
3. 用户想查订单（"我买的到哪了""帮我查下单"）时调用 query_my_orders；
   用户报了订单号就把订单号传给它；用户没报订单号就不传参数查最近的订单；
   不要用 query_my_orders 回答规则类问题，也不要凭空猜测订单状态；
4. 用户表达购买意向或询问商品（"有没有…推荐""XX 多少钱""XX 怎么样"）时，
   调用 recommend_products 查真实在售商品，按返回结果推荐并附上价格，不要编造商品；
5. 打招呼、闲聊、询问你能做什么这类不需要查资料的问题，可以直接回答；
6. 回答要简洁、准确、友好，符合电商客服语气；可结合对话历史理解上下文，
   若用户用了"那这个呢""我的那单"之类的指代，请自行改写成完整问题后再检索；
7. 输出格式：用短段落和换行分点，重点可用 **加粗** 突出（页面支持加粗渲染），
   不要用 markdown 标题、表格或代码块；查到订单后先给结论（如"已发货"）再给细节；
   推荐商品按工具返回的真实商品名列出（前端会同步展示商品卡片，正文只做一两句说明）。

售后操作（重要，必须严格遵守）：
8. 只有用户明确要求"取消订单 / 申请退款 / 修改收货地址"时才调用 propose_after_sales_action，
   不允许自行推测用户意图后发起；
9. 发起前先用 query_my_orders 查到真实订单号；修改地址还要先调用 list_my_addresses 拿到地址 ID。
   订单号、地址 ID 一律来自工具结果，绝不能编造；
10. 该工具只生成"待确认提案"，不会真正执行。调用后必须告诉用户
    "已生成操作确认卡片，请点击「确认执行」"，绝不能声称已经取消/退款/改址成功；
11. 用户只是想了解流程时，用 search_knowledge_base 回答政策，不要发起提案。"""


def _build_messages(history: list, question: str) -> list[dict]:
    """组装模型输入：系统提示 + 历史对话 + 当前问题"""
    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": question})
    return messages


AGENT_TIMEOUT_ANSWER = (
    "本次问题处理时间较长，已暂停继续查询。请缩小问题范围后重试，或联系人工客服。"
)


def _run_agent(messages: list[dict], db: Session, sources: list[dict], direct: list[str],
               tenant_id: int | None = None, user_id: int | None = None,
               session_id: int | None = None, trace: dict | None = None):
    """ReAct 工具调用循环。

    每一轮让模型自主决定：调用工具（执行后把结果喂回模型，进入下一轮），
    还是直接给出答案（循环结束）。最多 agent_max_steps 轮，防止模型无限调用工具。

    每执行一次工具就 yield 一条 (展示文案, 前端卡片payload)，供流式接口推给前端；
    命中的引用来源就地累加到 sources。

    direct：单元素列表。若模型全程没调用任何工具就直接作答（如打招呼），
    把它的答案放进去，调用方据此省掉一次多余的模型调用。

    trace：本轮问答的可信度线索（是否用过知识库、各次检索的充分性结论），
    供调用方在生成后做 claim 校验并推 verify 事件。

    【超时预算】同步 DB 工具无法安全强杀线程，因此用"总时长预算"控制：
    每轮模型调用前、每次工具执行前检查 deadline；超时后立即收口并给用户可读提示。
    """
    trace = trace if trace is not None else {}
    deadline = time.monotonic() + settings.agent_timeout_seconds
    called_tool = False
    for _ in range(settings.agent_max_steps):
        if time.monotonic() > deadline:
            direct.append(AGENT_TIMEOUT_ANSWER)
            return

        assistant_msg = generator.chat_with_tools(messages, tools.TOOLS)
        tool_calls = assistant_msg.get("tool_calls")

        # 模型没调工具 —— 说明它准备作答，循环结束。
        # 注意：这里绝不能把这条 assistant 消息追加进 messages，
        # 否则 messages 以 assistant 结尾，后续流式调用会变成「续写」而不是「回答」。
        if not tool_calls:
            if not called_tool:
                direct.append(assistant_msg.get("content") or "")
            return

        called_tool = True
        # 把模型的工具调用请求记入对话，再逐个执行
        messages.append(assistant_msg)
        timed_out = False
        for tc in tool_calls:
            # 超时后仍要为每个 tool_call 补一条 tool 响应，
            # 否则 messages 里会有"只有调用、没有结果"的悬空工具调用
            if time.monotonic() > deadline:
                timed_out = True
            if timed_out:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": "工具执行超时，未返回结果。",
                })
                continue

            name = tc["function"]["name"]
            args = tools.parse_arguments(tc["function"]["arguments"])
            # 只要尝试过知识库就进入校验：即使工具执行失败（Milvus/模型不可用），
            # 后续回答也应被标记为「没有证据支撑」，提示用户转人工核实
            if name == "search_knowledge_base":
                trace["kb_used"] = True
            yield tools.tool_label(name, args), None

            # session_id 由服务端注入，用于把写操作提案绑定到当前会话
            result = tools.execute_tool(
                name, args, db, tenant_id, user_id, session_id
            )
            sources.extend(result.sources)
            if result.meta:
                # 方向 D：记录本次检索的路由与缓存状态，随 meta 事件推给前端
                trace["route"] = result.meta.get("route") or trace.get("route")
                trace["retrieval"] = (
                    result.meta.get("retrieval") or trace.get("retrieval")
                )
                if result.meta.get("route", {}).get("strategy") == "none":
                    # 闲聊被路由为「不检索」，不能算作证据不足
                    trace["kb_used"] = False
                if result.meta.get("kb_used"):
                    trace["kb_used"] = True
                    trace.setdefault("sufficiencies", []).append(
                        result.meta.get("sufficiency") or {}
                    )
            elif name == "search_knowledge_base":
                # 工具执行失败（Milvus / Embedding 不可用等）也要留下门控结论，
                # 否则后续回答既没有证据、又没有「证据不足」提示
                trace.setdefault("sufficiencies", []).append({
                    "level": "insufficient",
                    "score": 0.0,
                    "hit_count": 0,
                    "reason": "知识库检索失败或未返回结果",
                })

            # 工具结果以 tool 角色喂回模型，供其下一轮推理
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result.text,
            })
            if result.payload:
                yield result.payload.get("type", ""), result.payload

        if timed_out:
            direct.append(AGENT_TIMEOUT_ANSWER)
            return


def _dedup_sources(sources: list[dict]) -> list[dict]:
    """同一片段可能被多轮检索命中，按 (doc_id, chunk_index) 去重"""
    seen = set()
    result = []
    for s in sources:
        key = (s["doc_id"], s["chunk_index"])
        if key in seen:
            continue
        seen.add(key)
        result.append(s)
    return result


def _fallback_answer(db: Session, question: str, tenant_id: int | None,
                     user_id: int | None, sources: list[dict]) -> str:
    """模型不可用时的降级回答：直接摘录知识库原文，保证有响应且可溯源

    sources 为空说明模型在第一轮就失败了（还没调过工具），
    此时用问题本身做一次确定性检索补上引用。
    """
    if not sources:
        try:
            result = tools.execute_tool(
                "search_knowledge_base", {"query": question},
                db, tenant_id=tenant_id, user_id=user_id,
            )
            sources.extend(result.sources)
        except Exception:
            pass

    snippets = []
    for source in _dedup_sources(sources)[:3]:
        text = " ".join((source.get("text") or "").split())
        if text:
            snippets.append(f"- {text[:180]}")
    if not snippets:
        return (
            "AI 服务暂时不可用（模型连接失败或未配置），知识库也没有检索到相关内容。"
            "请稍后重试，或联系人工客服处理。"
        )
    return (
        "AI 服务暂时不可用（模型连接失败或未配置）。"
        "以下是从知识库检索到的相关资料，供您参考：\n\n"
        + "\n\n".join(snippets)
        + "\n\n以上为知识库原文摘录，如需进一步判断请联系人工客服核实。"
    )


def _worst_sufficiency(items: list[dict] | None) -> dict | None:
    """一轮问答可能检索多次，取最保守（最差）的充分性结论"""
    if not items:
        return None
    rank = {"sufficient": 2, "partial": 1, "insufficient": 0}
    return min(items, key=lambda item: rank.get(item.get("level"), 0))


def _attach_source_verdicts(sources: list[dict], verification: dict) -> None:
    """把引用级 verdict 写回 sources（非流式响应直接带出，流式由前端按 key 合并）"""
    reports = {
        (item["doc_id"], item["chunk_index"]): item
        for item in verification.get("sources", [])
    }
    for source in sources:
        report = reports.get((source["doc_id"], source["chunk_index"]))
        if report:
            source["verdict"] = report["verdict"]
            source["confidence"] = report["confidence"]


def _verification_message(result: dict) -> str | None:
    """把校验结论翻译成用户能看懂的一句话"""
    if result.get("refuse"):
        return "知识库证据不足，本次回答仅供参考；建议转人工客服核实后再操作。"
    if result.get("low_confidence"):
        percent = round(result.get("faithfulness", 0) * 100)
        issues = []
        if result.get("unsupported"):
            issues.append(f"{result['unsupported']} 句未在知识库中找到直接依据")
        if result.get("partial"):
            issues.append(f"{result['partial']} 句仅部分匹配")
        detail = "；".join(issues) or "证据覆盖不足"
        return (
            f"校验发现{detail}（句子忠实度 {percent}%），"
            "请核对引用；如需准确答复可转人工客服。"
        )
    if result.get("total"):
        percent = round(result.get("faithfulness", 0) * 100)
        return f"已校验 {result['total']} 句回答，均有知识库依据（忠实度 {percent}%）。"
    return None


def _build_verification(answer: str, sources: list[dict], trace: dict) -> dict | None:
    """生成后校验：claim 级支撑 + 引用 verdict + 低置信提示

    只有本轮真的用过知识库才校验；纯闲聊、查订单等没有知识库证据的回答不适用，
    避免把「您的订单已发货」误判成幻觉。
    """
    if not settings.faithfulness_enabled or not trace.get("kb_used"):
        return None

    result = verifier.verify_answer(
        answer,
        sources,
        max_claims=settings.verifier_max_claims,
        threshold=settings.faithfulness_threshold,
    )
    sufficiency = _worst_sufficiency(trace.get("sufficiencies"))
    result["sufficiency"] = sufficiency
    result["refuse"] = verifier.should_refuse(sources, sufficiency)
    if result["refuse"]:
        result["low_confidence"] = True
    result["message"] = _verification_message(result)
    _attach_source_verdicts(sources, result)
    return result


def _resolve_session(db: Session, question: str, session_id: int | None,
                     tenant_id: int | None) -> tuple[int, list]:
    """确定本次问答的会话：没有 session_id 就新建，有则校验归属租户后读取历史"""
    if session_id is None:
        session = session_service.create_session(db, title=question[:20], tenant_id=tenant_id)
        return session.id, []
    if not session_service.get_session(db, session_id, tenant_id):
        raise NotFoundError("会话不存在")
    return session_id, session_service.get_history(db, session_id)


def ask(db: Session, question: str, session_id: int | None = None,
        tenant_id: int | None = None, user_id: int | None = None) -> ChatResponse:
    """问答主流程（Agent 版，一次性返回）"""
    # 1. 处理会话：没传 session_id 则新建
    session_id, history = _resolve_session(db, question, session_id, tenant_id)

    # 2. Agent 循环：模型自主决定调用哪些工具
    messages = _build_messages(history, question)
    sources: list[dict] = []
    direct: list[str] = []
    trace: dict = {}
    try:
        for _ in _run_agent(
            messages, db, sources, direct, tenant_id, user_id, session_id, trace=trace
        ):
            pass  # 非流式接口不展示中间步骤
        # 3. 生成最终答案：模型直接答完了就用它，否则基于工具结果再生成
        answer = direct[0] if direct else generator.generate_text(messages)
    except Exception as exc:
        # 模型网络不可用 / 未配置 Key：降级为知识库摘录，避免整条问答 500
        if not isinstance(exc, ServiceUnavailableError) and not generator.is_llm_unavailable(exc):
            raise
        answer = _fallback_answer(db, question, tenant_id, user_id, sources)

    # 4. 可信回答校验：充分性门控结论 + claim 级支撑 + 引用 verdict
    deduped = _dedup_sources(sources)
    verification = _build_verification(answer, deduped, trace)

    # 5. 保存本轮消息（用户问题 + AI 回答）
    session_service.save_message(db, session_id, "user", question, tenant_id)
    msg = session_service.save_message(db, session_id, "assistant", answer, tenant_id)
    # 6. 记录问答事件，供知识缺口聚类与 FAQ 草稿使用
    qa_event_service.record(
        db, tenant_id=tenant_id, user_id=user_id, session_id=session_id,
        message_id=msg.id, query=question, answer=answer,
        sources=deduped, verification=verification, trace=trace,
    )

    return ChatResponse(
        answer=answer,
        sources=[Source(**s) for s in deduped],
        session_id=session_id,
        message_id=msg.id,
        verification=verification,
    )


def ask_stream(db: Session, question: str, session_id: int | None = None,
               tenant_id: int | None = None, user_id: int | None = None):
    """流式问答：Agent 先自主调用工具，再流式输出答案（SSE 事件生成器）"""
    # 1. 会话处理（校验归属租户）
    session_id, history = _resolve_session(db, question, session_id, tenant_id)

    # 2. Agent 循环：每执行一次工具就推 step 事件，附带结构化卡片 payload
    messages = _build_messages(history, question)
    sources: list[dict] = []
    direct: list[str] = []
    trace: dict = {}
    llm_error: Exception | None = None
    try:
        for label, payload in _run_agent(
            messages, db, sources, direct, tenant_id, user_id, session_id, trace=trace
        ):
            if payload:
                # 工具的结构化结果（products / orders / action），原样推给前端渲染
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'step', 'label': label}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        # 模型不可用（断网 / 超时 / 未配置 Key）不中断对话，改为知识库降级回答；
        # 其他异常仍向上抛，避免把程序 bug 伪装成“AI 不可用”
        if isinstance(exc, ServiceUnavailableError) or generator.is_llm_unavailable(exc):
            llm_error = exc
        else:
            raise

    # 3. 保存用户消息
    session_service.save_message(db, session_id, "user", question, tenant_id)

    # 4. 先发 meta（会话ID + 引用来源）；verdict 要等答案生成后才能算，
    #    因此引用级校验结果放在随后的 verify 事件里，由前端按 doc_id+chunk_index 合并
    fallback_answer = None
    if llm_error is not None:
        fallback_answer = _fallback_answer(
            db, question, tenant_id, user_id, sources
        )
    deduped = _dedup_sources(sources)
    meta_event = {
        "type": "meta",
        "sources": deduped,
        "session_id": session_id,
    }
    if trace.get("route"):
        meta_event["route"] = trace["route"]
    if trace.get("retrieval"):
        meta_event["retrieval"] = trace["retrieval"]
    yield f"data: {json.dumps(meta_event, ensure_ascii=False)}\n\n"

    # 5. 输出最终答案
    full_answer = ""
    if fallback_answer is not None:
        full_answer = fallback_answer
        yield f"data: {json.dumps({'type': 'delta', 'content': full_answer}, ensure_ascii=False)}\n\n"
    elif direct:
        # 模型全程没查资料、已直接作答，不必再调一次模型
        full_answer = direct[0]
        yield f"data: {json.dumps({'type': 'delta', 'content': full_answer}, ensure_ascii=False)}\n\n"
    else:
        # 流式生成（失败则降级为一次性返回；模型不可用则摘录知识库）
        try:
            for chunk in generator.stream_answer(messages):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            if isinstance(exc, ServiceUnavailableError) or generator.is_llm_unavailable(exc):
                full_answer = _fallback_answer(
                    db, question, tenant_id, user_id, sources
                )
                yield f"data: {json.dumps({'type': 'delta', 'content': full_answer}, ensure_ascii=False)}\n\n"
            else:
                raise

    # 6. 可信回答校验：逐句找证据，低置信时提示转人工；只新增事件，不改动旧协议
    verification = _build_verification(full_answer, deduped, trace)
    if verification:
        event = {"type": "verify", **verification}
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    # 7. 保存 AI 回答，发 done
    msg = session_service.save_message(db, session_id, "assistant", full_answer, tenant_id)
    qa_event_service.record(
        db, tenant_id=tenant_id, user_id=user_id, session_id=session_id,
        message_id=msg.id, query=question, answer=full_answer,
        sources=deduped, verification=verification, trace=trace,
    )
    yield f"data: {json.dumps({'type': 'done', 'message_id': msg.id}, ensure_ascii=False)}\n\n"

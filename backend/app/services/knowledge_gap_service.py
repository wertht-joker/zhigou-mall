"""知识缺口闭环：问答事件聚类 → FAQ 草稿 → 一键入库

只用规则与集合相似度，不依赖外部模型，保证离线/测试可复现：
1. 从 qa_events 中筛出「点踩 / 检索无结果 / 证据不足 / 忠实度偏低」的坏例；
2. 按问题文本的字符二元组 Jaccard 相似度做贪心聚类；
3. 为每个缺口生成带证据指针的 FAQ 草稿（不编造答案，标准答案留待人工补充）；
4. 发布后把对应问题标记为已处理，形成可观测的闭环。
"""
import hashlib
import re
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.models.document import Document
from app.models.qa_event import QaEvent
from app.models.tenant import Tenant
from app.rag import retriever
from app.repositories.qa_event_repository import QaEventRepository
from app.services import document_service

# 检索类链路（用于识别「检索了但没召回」）
RETRIEVAL_ROUTES = {"vector", "hybrid", "hybrid+rerank", "multi_query"}

_PUNCT_RE = re.compile(r"[\s，。！？、；：,.!?;:（）()\[\]【】\"'“”‘’~·—\-_/\\]+")
_STOPWORDS = {
    "你们", "我们", "这个", "那个", "可以", "怎么", "如何", "什么", "是否",
    "请问", "一下", "支持", "需要", "能够", "有没有", "可以吗", "吗", "呢",
}


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", (text or "").lower())


def _bigrams(text: str) -> set[str]:
    text = _normalize(text)
    if len(text) <= 1:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _similarity(a: str, b: str) -> float:
    """重叠系数：短问题的大部分片段被长问题覆盖，即视为同一意图

    电商问题普遍很短（6-10 字），用 Jaccard 会把「支持花呗分期吗」和
    「可以用花呗分期付款吗」判成不同问题，因此这里用 |A∩B| / min(|A|,|B|)。
    """
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def _issues(event: QaEvent) -> list[str]:
    """一个坏例命中的问题类型（可多选）"""
    causes = []
    if event.feedback == "down":
        causes.append("顾客点踩")
    if (event.route in RETRIEVAL_ROUTES) and (event.sources_count or 0) == 0:
        causes.append("检索无结果")
    if event.sufficiency == "insufficient":
        causes.append("证据不足")
    if event.faithfulness is not None and event.faithfulness < 0.6:
        causes.append("忠实度偏低")
    return causes


def _is_problem(event: QaEvent) -> bool:
    return bool(_issues(event))


def _cluster(events: list[QaEvent], threshold: float = 0.45) -> list[list[QaEvent]]:
    """贪心聚类：与簇内代表问题的相似度达到阈值即归入同一缺口"""
    clusters: list[list[QaEvent]] = []
    for event in events:
        placed = False
        for cluster in clusters:
            if any(_similarity(event.query, other.query) >= threshold
                   for other in cluster[:5]):
                cluster.append(event)
                placed = True
                break
        if not placed:
            clusters.append([event])
    return clusters


def _tenant_names(db: Session, tenant_ids: set[int]) -> dict[int, str]:
    if not tenant_ids:
        return {}
    rows = db.query(Tenant.id, Tenant.name).filter(Tenant.id.in_(tenant_ids)).all()
    return {row[0]: row[1] for row in rows}


def list_gaps(db: Session, days: int = 30,
              tenant_id: int | None = None) -> dict:
    """知识缺口看板：先按商家隔离，再在商家内按问题聚类

    tenant_id 为空时展示全平台，但不同商家的问题绝不会聚成同一缺口，
    保证「谁的缺口谁负责」。
    """
    events = QaEventRepository(db).list_recent(days, tenant_id)
    problems = [event for event in events if _is_problem(event)]

    names = _tenant_names(db, {e.tenant_id for e in problems if e.tenant_id})
    by_tenant: dict[int | None, list[QaEvent]] = {}
    for event in problems:
        by_tenant.setdefault(event.tenant_id, []).append(event)

    gaps = []
    for owner_id, tenant_events in by_tenant.items():
        tenant_name = names.get(owner_id, f"租户#{owner_id}") if owner_id else "平台"
        for group in _cluster(tenant_events):
            queries: list[str] = []
            for event in group:
                query = (event.query or "").strip()
                if query and query not in queries:
                    queries.append(query)
            causes: list[str] = []
            for event in group:
                for cause in _issues(event):
                    if cause not in causes:
                        causes.append(cause)
            faithfulness = [
                e.faithfulness for e in group if e.faithfulness is not None
            ]
            gap_id = hashlib.sha1(
                (f"{owner_id}|" + "|".join(sorted(_normalize(q) for q in queries))).encode()
            ).hexdigest()[:12]
            gaps.append({
                "id": gap_id,
                "tenant_id": owner_id,
                "tenant_name": tenant_name,
                "theme": queries[0][:40] if queries else "未命名问题",
                "count": len(group),
                "queries": queries[:5],
                "causes": causes,
                "tenants": [tenant_name],
                "avg_faithfulness": (
                    round(sum(faithfulness) / len(faithfulness), 3)
                    if faithfulness else None
                ),
                "last_seen": max(e.created_at for e in group).isoformat(),
            })

    gaps.sort(key=lambda gap: (-gap["count"], gap["last_seen"]))
    return {
        "window_days": days,
        "tenant_id": tenant_id,
        "total_events": len(events),
        "problem_events": len(problems),
        "gap_count": len(gaps),
        "down_count": sum(1 for e in problems if e.feedback == "down"),
        "no_hit_count": sum(
            1 for e in problems
            if e.route in RETRIEVAL_ROUTES and (e.sources_count or 0) == 0
        ),
        "insufficient_count": sum(
            1 for e in problems if e.sufficiency == "insufficient"
        ),
        "gaps": gaps[:20],
    }


def _keywords(queries: list[str], limit: int = 4) -> list[str]:
    """从问题中提取用于匹配文档名的关键词（优先 2-4 字中文词）"""
    words: list[str] = []
    for query in queries:
        normalized = _normalize(query)
        for size in (4, 3, 2):
            for start in range(0, max(len(normalized) - size + 1, 0)):
                token = normalized[start:start + size]
                if token in _STOPWORDS or token.isdigit():
                    continue
                if token not in words:
                    words.append(token)
                if len(words) >= limit:
                    return words
    return words


def _related_docs(db: Session, queries: list[str],
                  tenant_id: int | None = None) -> list[Document]:
    keywords = _keywords(queries)
    if not keywords:
        return []
    conditions = [Document.name.like(f"%{word}%") for word in keywords]
    query = db.query(Document).filter(Document.status == "done", or_(*conditions))
    if tenant_id is None:
        query = query.filter(Document.tenant_id.is_(None))
    else:
        query = query.filter(Document.tenant_id == tenant_id)
    docs = query.limit(50).all()
    docs.sort(key=lambda doc: -sum(word in doc.name for word in keywords))
    return docs[:5]


def build_draft(db: Session, queries: list[str],
                tenant_id: int | None = None) -> dict:
    """生成带证据指针的 FAQ 草稿；没有依据时明确提示，不自动编答案"""
    queries = [q.strip() for q in (queries or []) if q and q.strip()]
    if not queries:
        raise BadRequestError("缺少需要生成草稿的问题")
    title = f"FAQ：{queries[0][:30]}"
    related = _related_docs(db, queries, tenant_id)

    evidence = []
    for doc in related:
        version = f" v{doc.version}" if doc.policy_key else ""
        effective = ""
        if doc.effective_from:
            effective = f"，生效于 {doc.effective_from.strftime('%Y-%m-%d')}"
        evidence.append(f"- 《{doc.name}》{version}{effective}")
    if not evidence:
        evidence = ["- 暂未匹配到现有文档，请补充业务口径后再发布。"]

    lines = [
        f"# {title}",
        "",
        "> 本文由 AI 客服知识缺口自动汇总生成，标准答案需人工核对后发布。",
        "",
        "## 常见问题",
        *[f"{index}. {query}" for index, query in enumerate(queries[:5], 1)],
        "",
        "## 标准答案",
        "<!-- 请在此补充准确、可执行的标准答复；避免承诺未确认的时效或金额。 -->",
        "",
        "## 依据与口径",
        *evidence,
        "",
        "## 适用说明",
        "- 自发布之日起生效；如政策调整，请上传新版本并标注生效时间。",
        "",
    ]
    return {
        "title": title,
        "content": "\n".join(lines),
        "queries": queries[:5],
        "related_docs": [
            {"id": doc.id, "name": doc.name, "version": doc.version,
             "policy_key": doc.policy_key}
            for doc in related
        ],
    }


def run_regression(db: Session, doc_id: int,
                   tenant_id: int | None = None, top_k: int = 5) -> dict:
    """FAQ 发布后的命中率回归

    用当初触发缺口的原问题重新检索，检查新 FAQ 是否进入 Top-K。
    hit_rate 是最直观的指标：发布后仍召不回，说明标题/内容需要调整。
    """
    queries = QaEventRepository(db).list_resolved_queries(doc_id, tenant_id)
    details = []
    hits = 0
    mrr = 0.0
    for query in queries:
        try:
            results, meta = retriever.search_with_meta(
                query, top_k=top_k, tenant_id=tenant_id,
                allow_semantic_cache=False,
            )
        except Exception as exc:  # 回归失败不能影响 FAQ 发布本身
            results, meta = [], {"strategy": "error", "error": str(exc)}
        rank = None
        score = None
        for index, hit in enumerate(results, 1):
            if str(hit.get("doc_id")) == str(doc_id):
                rank = index
                score = hit.get("score")
                break
        if rank:
            hits += 1
            mrr += 1 / rank
        details.append({
            "query": query,
            "hit": bool(rank),
            "rank": rank,
            "score": round(float(score), 4) if score is not None else None,
            "strategy": meta.get("strategy"),
            "error": meta.get("error"),
        })
    total = len(queries)
    return {
        "document_id": doc_id,
        "tenant_id": tenant_id,
        "top_k": top_k,
        "total": total,
        "hits": hits,
        "hit_rate": round(hits / total, 4) if total else 0.0,
        "mrr": round(mrr / total, 4) if total else 0.0,
        "details": details,
    }


def publish_draft(db: Session, title: str, content: str,
                  queries: list[str], category_id: int | None = None,
                  tenant_id: int | None = None) -> dict:
    """把草稿发布为知识库文档，关闭该商家的缺口，并立即做命中率回归

    文档与缺口都以 tenant_id 为边界：A 商家发布 FAQ 不会关闭 B 商家的缺口。
    """
    doc = document_service.create_text_document(
        db, title, content, tenant_id=tenant_id, category_id=category_id
    )
    handled = QaEventRepository(db).mark_handled(
        queries or [], tenant_id, resolved_doc_id=doc.id
    )
    regression = run_regression(db, doc.id, tenant_id)
    return {
        "document_id": doc.id,
        "name": doc.name,
        "chunk_count": doc.chunk_count,
        "handled_events": handled,
        "published_at": datetime.now().isoformat(),
        "regression": regression,
    }

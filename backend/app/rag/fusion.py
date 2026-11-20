"""RRF（Reciprocal Rank Fusion）融合多路召回

score(d) = Σ 1 / (k + rank_i(d))

只看每条通路里的排名，不比较各通路的分数量纲，因此「向量分数」与
「BM25 分数」可以直接融合，无需归一化，简单且稳健。

【k 的意义】（默认 60，面试追问点）
  rank=1 得 1/61、rank=2 得 1/62——单路内部相邻名次的分差被压平，
  只有「两路都靠前」的文档才会浮到最上面；k 越大越强调"多路共识"，
  k 越小越偏袒单路冠军。可以在 evals/ 里用 hit rate / MRR 调参验证。

【vs 加权归一化融合】向量分（COSINE 0~1）与 BM25 分（0~+∞）量纲不可比，
  直接加权必须先归一化（min/max 或 z-score，对分布敏感、难维护）；
  RRF 只消费排名，天然免疫量纲问题——工程上最稳的默认选择。
"""


def rrf(rankings: list[list[dict]], k: int = 60) -> list[dict]:
    """把多路召回结果融合成一个按融合分降序的列表

    rankings: 每路都是一批命中（含 doc_id / chunk_index / text），按各自排名排序
    返回：按 (doc_id, chunk_index) 去重后的融合结果，score 为 RRF 分数
    """
    merged: dict[tuple, dict] = {}
    for hits in rankings:
        for rank, hit in enumerate(hits, start=1):
            key = (hit.get("doc_id"), hit.get("chunk_index"))
            entry = merged.get(key)
            if entry is None:
                entry = dict(hit)
                entry["score"] = 0.0
                merged[key] = entry
            entry["score"] += 1.0 / (k + rank)

    return sorted(merged.values(), key=lambda item: item["score"], reverse=True)

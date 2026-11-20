"""检索链路轻量指标（进程内滑动窗口）

记录每次检索的策略、缓存命中情况与耗时，供：
- `/api/v1/metrics/retrieval` 演示面板；
- 离线评测脚本对比「固定链路 vs 自适应路由」的成本收益。

不引入 Prometheus 依赖：单进程演示足够；多 worker 部署时应换成
Prometheus / OpenTelemetry 汇总。
"""
from collections import Counter, deque
from threading import Lock

_MAX_SAMPLES = 500

_latencies: deque[float] = deque(maxlen=_MAX_SAMPLES)
_counters: Counter = Counter()
_lock = Lock()


def record(strategy: str, cache: str, elapsed_ms: float, hits: int) -> None:
    """记录一次检索：strategy=路由策略，cache=exact/semantic/miss/off"""
    with _lock:
        _counters["retrieval_total"] += 1
        _counters[f"strategy:{strategy}"] += 1
        _counters[f"cache:{cache}"] += 1
        _counters["hits_total"] += hits
        _latencies.append(float(elapsed_ms))


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, int(round((p / 100) * (len(values) - 1))))
    return round(values[index], 2)


def snapshot() -> dict:
    with _lock:
        total = _counters["retrieval_total"]
        latencies = sorted(_latencies)
        strategies = {
            key.split(":", 1)[1]: value
            for key, value in _counters.items()
            if key.startswith("strategy:")
        }
        caches = {
            key.split(":", 1)[1]: value
            for key, value in _counters.items()
            if key.startswith("cache:")
        }
        hits_total = _counters["hits_total"]

    cache_hits = caches.get("exact", 0) + caches.get("semantic", 0)
    return {
        "retrieval_total": total,
        "cache": caches,
        "cache_hit_rate": round(cache_hits / total, 4) if total else 0.0,
        "strategy_distribution": strategies,
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
        },
        "avg_hits": round(hits_total / total, 2) if total else 0.0,
    }


def reset() -> None:
    """清空指标（测试/评测用）"""
    with _lock:
        _counters.clear()
        _latencies.clear()

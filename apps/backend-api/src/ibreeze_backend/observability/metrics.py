"""In-memory request metrics collection."""

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_request_counts: dict[str, int] = defaultdict(int)
_status_counts: dict[int, int] = defaultdict(int)
_duration_sum: dict[str, float] = defaultdict(float)
_duration_count: dict[str, int] = defaultdict(int)
_started_at: float = time.time()


def record_request(duration: float, method: str, path: str, status_code: int) -> None:
    key = f"{method} {path}"
    with _lock:
        _request_counts[key] += 1
        _status_counts[status_code] += 1
        _duration_sum[key] += duration
        _duration_count[key] += 1


def get_metrics() -> dict:
    with _lock:
        uptime = time.time() - _started_at
        by_endpoint: dict[str, dict] = {}
        for key in _request_counts:
            count = _request_counts[key]
            total_duration = _duration_sum[key]
            by_endpoint[key] = {
                "count": count,
                "avg_duration_ms": round((total_duration / count) * 1000, 2) if count else 0,
            }
        return {
            "uptime_seconds": round(uptime, 2),
            "total_requests": sum(_request_counts.values()),
            "status_codes": dict(_status_counts),
            "by_endpoint": by_endpoint,
        }

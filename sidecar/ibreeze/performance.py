"""Performance configuration and utilities."""
import time
from functools import wraps
from typing import Any, Callable


class PerformanceMetrics:
    def __init__(self):
        self.request_count = 0
        self.total_duration = 0.0

    def record_request(self, duration: float):
        self.request_count += 1
        self.total_duration += duration

    @property
    def average_duration(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_duration / self.request_count

    def reset(self):
        self.request_count = 0
        self.total_duration = 0.0


metrics = PerformanceMetrics()


def track_performance(func: Callable) -> Callable:
    """Decorator to track function performance."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.perf_counter() - start
            metrics.record_request(duration)
    return wrapper

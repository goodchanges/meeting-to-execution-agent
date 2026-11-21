from collections import deque
from math import ceil
from threading import Lock


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.routes: dict[str, tuple[int, int, deque[float]]] = {}

    def record(self, route: str, status: int, duration: float, include_latency: bool):
        with self.lock:
            total, errors, samples = self.routes.get(route, (0, 0, deque(maxlen=512)))
            if include_latency:
                samples.append(duration)
            self.routes[route] = (total + 1, errors + int(status >= 500), samples)

    def snapshot(self):
        result = {}
        with self.lock:
            for route, (count, errors, samples) in self.routes.items():
                values = sorted(samples)
                result[route] = {
                    "requests": count,
                    "server_errors": errors,
                    "server_error_rate": errors / count,
                    "sample_count": len(values),
                    "p50_ms": values[ceil(len(values) * 0.5) - 1] if values else None,
                    "p95_ms": values[ceil(len(values) * 0.95) - 1] if values else None,
                }
        return result

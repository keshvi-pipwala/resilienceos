"""
Shared utilities for all ResilienceOS microservices.
Provides chaos header processing, metrics collection, and health reporting.
"""
import time
import random
import asyncio
import os
from typing import Optional
from collections import deque
from threading import Lock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class ServiceMetrics:
    """Thread-safe metrics collector for a microservice."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = time.time()
        self._lock = Lock()
        self._request_count = 0
        self._error_count = 0
        self._latencies = deque(maxlen=1000)

        # Chaos state
        self.chaos_enabled = False
        self.chaos_latency_ms = 0
        self.chaos_error_rate = 0.0
        self.chaos_jitter_ms = 0

    def record_request(self, latency_ms: float, is_error: bool):
        with self._lock:
            self._request_count += 1
            if is_error:
                self._error_count += 1
            self._latencies.append(latency_ms)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._request_count

    @property
    def error_rate(self) -> float:
        with self._lock:
            if self._request_count == 0:
                return 0.0
            return self._error_count / self._request_count

    @property
    def avg_latency_ms(self) -> float:
        with self._lock:
            if not self._latencies:
                return 0.0
            return sum(self._latencies) / len(self._latencies)

    @property
    def p99_latency_ms(self) -> float:
        with self._lock:
            if not self._latencies:
                return 0.0
            sorted_l = sorted(self._latencies)
            idx = int(len(sorted_l) * 0.99)
            return sorted_l[min(idx, len(sorted_l) - 1)]

    def health_status(self) -> str:
        er = self.error_rate
        lat = self.avg_latency_ms
        if er > 0.5 or lat > 2000:
            return "unhealthy"
        if er > 0.1 or lat > 500:
            return "degraded"
        return "healthy"

    def to_health_dict(self) -> dict:
        return {
            "status": self.health_status(),
            "uptime_seconds": round(self.uptime_seconds, 2),
            "request_count": self.request_count,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "chaos_enabled": self.chaos_enabled,
        }

    def to_prometheus_text(self) -> str:
        svc = self.service_name.replace("-", "_")
        lines = [
            f'# HELP {svc}_requests_total Total HTTP requests',
            f'# TYPE {svc}_requests_total counter',
            f'{svc}_requests_total {self.request_count}',
            f'# HELP {svc}_error_rate Current error rate (0-1)',
            f'# TYPE {svc}_error_rate gauge',
            f'{svc}_error_rate {round(self.error_rate, 4)}',
            f'# HELP {svc}_avg_latency_ms Average request latency in milliseconds',
            f'# TYPE {svc}_avg_latency_ms gauge',
            f'{svc}_avg_latency_ms {round(self.avg_latency_ms, 2)}',
            f'# HELP {svc}_p99_latency_ms P99 request latency in milliseconds',
            f'# TYPE {svc}_p99_latency_ms gauge',
            f'{svc}_p99_latency_ms {round(self.p99_latency_ms, 2)}',
            f'# HELP {svc}_uptime_seconds Service uptime in seconds',
            f'# TYPE {svc}_uptime_seconds gauge',
            f'{svc}_uptime_seconds {round(self.uptime_seconds, 2)}',
            f'# HELP {svc}_chaos_active Whether chaos is currently active',
            f'# TYPE {svc}_chaos_active gauge',
            f'{svc}_chaos_active {1 if self.chaos_enabled else 0}',
        ]
        return "\n".join(lines) + "\n"


class ChaosMiddleware(BaseHTTPMiddleware):
    """
    Middleware that processes chaos control headers and applies fault injection.
    Headers: X-Chaos-Enabled, X-Chaos-Latency-Ms, X-Chaos-Error-Rate
    Also reads chaos state from the metrics object for agent-driven chaos.
    """

    def __init__(self, app, metrics: ServiceMetrics):
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next):
        # Skip chaos on health and metrics endpoints
        if request.url.path in ("/health", "/metrics"):
            start = time.time()
            response = await call_next(request)
            latency = (time.time() - start) * 1000
            is_error = response.status_code >= 500
            self.metrics.record_request(latency, is_error)
            return response

        # Read chaos from headers (per-request override)
        header_chaos_enabled = request.headers.get("X-Chaos-Enabled", "").lower() == "true"
        header_latency_ms = int(request.headers.get("X-Chaos-Latency-Ms", "0"))
        header_error_rate = float(request.headers.get("X-Chaos-Error-Rate", "0"))

        # Merge: header values take precedence, fallback to agent-driven state
        effective_latency = header_latency_ms if header_chaos_enabled else (
            self.metrics.chaos_latency_ms if self.metrics.chaos_enabled else 0
        )
        effective_error_rate = header_error_rate if header_chaos_enabled else (
            self.metrics.chaos_error_rate if self.metrics.chaos_enabled else 0.0
        )
        jitter = self.metrics.chaos_jitter_ms if self.metrics.chaos_enabled else 0

        # Apply latency injection
        if effective_latency > 0:
            delay_ms = effective_latency
            if jitter > 0:
                delay_ms += random.randint(0, jitter)
            await asyncio.sleep(delay_ms / 1000.0)

        # Apply error rate injection
        if effective_error_rate > 0 and random.random() < effective_error_rate:
            self.metrics.record_request(0, True)
            return Response(
                content='{"detail":"Service temporarily unavailable (chaos fault injected)"}',
                status_code=500,
                media_type="application/json"
            )

        start = time.time()
        response = await call_next(request)
        latency = (time.time() - start) * 1000 + effective_latency
        is_error = response.status_code >= 500
        self.metrics.record_request(latency, is_error)
        return response


def get_db_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://resilience:resilience@postgres:5432/resilienceos"
    )


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://redis:6380/0")

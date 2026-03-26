"""
ResilienceOS API Gateway (port 8000)
Routes requests to downstream services with circuit breaker logic and metrics.
"""
import time
import os
import sys
import httpx
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

sys.path.insert(0, "/app")
from services.shared import ServiceMetrics, ChaosMiddleware

metrics = ServiceMetrics("api-gateway")

SERVICE_URLS = {
    "user-service": os.getenv("USER_SERVICE_URL", "http://user-service:8001"),
    "product-service": os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8002"),
    "order-service": os.getenv("ORDER_SERVICE_URL", "http://order-service:8003"),
    "notification-service": os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8004"),
}

# Circuit breaker state per downstream service
circuit_breakers = {
    name: {
        "state": "closed",  # closed, open, half-open
        "failure_count": 0,
        "last_failure_time": 0,
        "failure_threshold": 5,
        "reset_timeout": 30,
    }
    for name in SERVICE_URLS
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("API Gateway starting up...")
    yield
    print("API Gateway shutting down...")


app = FastAPI(title="ResilienceOS API Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(ChaosMiddleware, metrics=metrics)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_circuit_breaker(service_name: str) -> bool:
    """Returns True if request should be allowed through."""
    cb = circuit_breakers.get(service_name)
    if not cb:
        return True

    if cb["state"] == "open":
        if time.time() - cb["last_failure_time"] > cb["reset_timeout"]:
            cb["state"] = "half-open"
            return True
        return False

    return True


def record_circuit_breaker_result(service_name: str, success: bool):
    cb = circuit_breakers.get(service_name)
    if not cb:
        return

    if success:
        cb["failure_count"] = 0
        cb["state"] = "closed"
    else:
        cb["failure_count"] += 1
        cb["last_failure_time"] = time.time()
        if cb["failure_count"] >= cb["failure_threshold"]:
            cb["state"] = "open"


async def proxy_request(service_name: str, path: str, request: Request) -> Response:
    if not check_circuit_breaker(service_name):
        raise HTTPException(
            status_code=503,
            detail=f"Circuit breaker open for {service_name}. Service unavailable."
        )

    base_url = SERVICE_URLS.get(service_name)
    if not base_url:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_name}")

    url = f"{base_url}{path}"
    method = request.method
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                method=method,
                url=url,
                content=body,
                headers=headers,
                params=dict(request.query_params),
            )
        record_circuit_breaker_result(service_name, resp.status_code < 500)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except httpx.TimeoutException:
        record_circuit_breaker_result(service_name, False)
        raise HTTPException(status_code=504, detail=f"Gateway timeout connecting to {service_name}")
    except httpx.ConnectError:
        record_circuit_breaker_result(service_name, False)
        raise HTTPException(status_code=503, detail=f"Cannot connect to {service_name}")


@app.get("/health")
async def health():
    return metrics.to_health_dict()


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    return metrics.to_prometheus_text()


@app.get("/status")
async def status():
    """Returns gateway status including circuit breaker states."""
    return {
        "service": "api-gateway",
        "health": metrics.to_health_dict(),
        "circuit_breakers": {
            name: {
                "state": cb["state"],
                "failure_count": cb["failure_count"],
            }
            for name, cb in circuit_breakers.items()
        },
        "downstream_services": list(SERVICE_URLS.keys()),
    }


# User service proxy routes
@app.api_route("/api/users", methods=["GET", "POST"])
async def proxy_users(request: Request):
    return await proxy_request("user-service", "/users", request)


@app.api_route("/api/users/{user_id}", methods=["GET", "PUT", "DELETE"])
async def proxy_user(user_id: int, request: Request):
    return await proxy_request("user-service", f"/users/{user_id}", request)


# Product service proxy routes
@app.api_route("/api/products", methods=["GET", "POST"])
async def proxy_products(request: Request):
    return await proxy_request("product-service", "/products", request)


@app.api_route("/api/products/{product_id}", methods=["GET", "PUT", "DELETE"])
async def proxy_product(product_id: int, request: Request):
    return await proxy_request("product-service", f"/products/{product_id}", request)


# Order service proxy routes
@app.api_route("/api/orders", methods=["GET", "POST"])
async def proxy_orders(request: Request):
    return await proxy_request("order-service", "/orders", request)


@app.api_route("/api/orders/{order_id}", methods=["GET", "PUT", "DELETE"])
async def proxy_order(order_id: int, request: Request):
    return await proxy_request("order-service", f"/orders/{order_id}", request)


# Chaos control endpoint (updates gateway's own chaos state)
@app.post("/chaos/configure")
async def configure_chaos(config: dict):
    metrics.chaos_enabled = config.get("enabled", False)
    metrics.chaos_latency_ms = config.get("latency_ms", 0)
    metrics.chaos_error_rate = config.get("error_rate", 0.0)
    metrics.chaos_jitter_ms = config.get("jitter_ms", 0)
    return {"status": "applied", "config": config}

"""
ResilienceOS Order Service (port 8003)
Creates orders by calling user-service and product-service.
Key service for demonstrating cascade failure behavior.
"""
import sys
import os
import json
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import redis.asyncio as aioredis

sys.path.insert(0, "/app")
from services.shared import ServiceMetrics, ChaosMiddleware, get_db_url, get_redis_url
from postgres.models import Base, Order

metrics = ServiceMetrics("order-service")

DATABASE_URL = get_db_url()
REDIS_URL = get_redis_url()
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8001")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8002")

engine = None
SessionLocal = None
redis_client = None

# Track inter-service call success rates
_dep_calls = {"user-service": {"success": 0, "total": 0}, "product-service": {"success": 0, "total": 0}}


def dep_success_rate(service: str) -> float:
    d = _dep_calls[service]
    if d["total"] == 0:
        return 1.0
    return d["success"] / d["total"]


def record_dep_call(service: str, success: bool):
    _dep_calls[service]["total"] += 1
    if success:
        _dep_calls[service]["success"] += 1


def init_db():
    global engine, SessionLocal
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    for attempt in range(10):
        try:
            init_db()
            print("Order Service: DB connected")
            break
        except Exception as e:
            print(f"Order Service: DB attempt {attempt+1}/10: {e}")
            await asyncio.sleep(3)

    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        print("Order Service: Redis connected")
    except Exception as e:
        print(f"Order Service: Redis connection failed: {e}")

    yield

    if redis_client:
        await redis_client.close()


app = FastAPI(title="ResilienceOS Order Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(ChaosMiddleware, metrics=metrics)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class OrderCreate(BaseModel):
    user_id: int
    product_id: int
    quantity: int = 1


class OrderResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    total_price: float
    status: str

    class Config:
        from_attributes = True


async def fetch_user(user_id: int) -> dict:
    """Fetch user from user-service. This is a real synchronous call — failures cascade."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{USER_SERVICE_URL}/users/{user_id}")
        record_dep_call("user-service", resp.status_code < 500)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        else:
            raise HTTPException(
                status_code=503,
                detail=f"User service returned {resp.status_code}: {resp.text[:200]}"
            )
    except HTTPException:
        raise
    except httpx.TimeoutException:
        record_dep_call("user-service", False)
        raise HTTPException(status_code=504, detail="Timeout connecting to user-service")
    except Exception as e:
        record_dep_call("user-service", False)
        raise HTTPException(status_code=503, detail=f"user-service unavailable: {str(e)}")


async def fetch_product(product_id: int) -> dict:
    """Fetch product from product-service. This is a real synchronous call — failures cascade."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}")
        record_dep_call("product-service", resp.status_code < 500)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        else:
            raise HTTPException(
                status_code=503,
                detail=f"Product service returned {resp.status_code}: {resp.text[:200]}"
            )
    except HTTPException:
        raise
    except httpx.TimeoutException:
        record_dep_call("product-service", False)
        raise HTTPException(status_code=504, detail="Timeout connecting to product-service")
    except Exception as e:
        record_dep_call("product-service", False)
        raise HTTPException(status_code=503, detail=f"product-service unavailable: {str(e)}")


@app.get("/health")
async def health():
    h = metrics.to_health_dict()
    h["dependency_health"] = {
        "user-service": round(dep_success_rate("user-service"), 4),
        "product-service": round(dep_success_rate("product-service"), 4),
    }
    return h


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    base = metrics.to_prometheus_text()
    extra = (
        f"# HELP order_service_user_dep_success_rate User service dependency success rate\n"
        f"# TYPE order_service_user_dep_success_rate gauge\n"
        f"order_service_user_dep_success_rate {round(dep_success_rate('user-service'), 4)}\n"
        f"# HELP order_service_product_dep_success_rate Product service dependency success rate\n"
        f"# TYPE order_service_product_dep_success_rate gauge\n"
        f"order_service_product_dep_success_rate {round(dep_success_rate('product-service'), 4)}\n"
    )
    return base + extra


@app.get("/orders")
async def list_orders(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    orders = db.query(Order).offset(skip).limit(limit).all()
    return [OrderResponse.from_orm(o) for o in orders]


@app.get("/orders/{order_id}")
async def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return OrderResponse.from_orm(order)


@app.post("/orders", status_code=201)
async def create_order(order_data: OrderCreate, db: Session = Depends(get_db)):
    # These real HTTP calls are where cascade failures originate
    user = await fetch_user(order_data.user_id)
    product = await fetch_product(order_data.product_id)

    if product.get("stock_quantity", 0) < order_data.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    total_price = round(product["price"] * order_data.quantity, 2)
    order = Order(
        user_id=order_data.user_id,
        product_id=order_data.product_id,
        quantity=order_data.quantity,
        total_price=total_price,
        status="pending"
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Publish order event to Redis for notification service
    if redis_client:
        try:
            event = json.dumps({
                "event": "order_created",
                "order_id": order.id,
                "user_id": order_data.user_id,
                "product_id": order_data.product_id,
                "total_price": total_price,
                "timestamp": time.time()
            })
            await redis_client.publish("order_events", event)
        except Exception:
            pass  # Redis unavailability should not block order creation

    return OrderResponse.from_orm(order)


@app.post("/chaos/configure")
async def configure_chaos(config: dict):
    metrics.chaos_enabled = config.get("enabled", False)
    metrics.chaos_latency_ms = config.get("latency_ms", 0)
    metrics.chaos_error_rate = config.get("error_rate", 0.0)
    metrics.chaos_jitter_ms = config.get("jitter_ms", 0)
    return {"status": "applied", "service": "order-service", "config": config}

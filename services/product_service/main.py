"""
ResilienceOS Product Service (port 8002)
Product catalog with Redis pub/sub for view event streaming.
"""
import sys
import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import redis.asyncio as aioredis

sys.path.insert(0, "/app")
from services.shared import ServiceMetrics, ChaosMiddleware, get_db_url, get_redis_url
from postgres.models import Base, Product

metrics = ServiceMetrics("product-service")

DATABASE_URL = get_db_url()
REDIS_URL = get_redis_url()

engine = None
SessionLocal = None
redis_client = None


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
            print("Product Service: DB connected")
            break
        except Exception as e:
            print(f"Product Service: DB attempt {attempt+1}/10: {e}")
            await asyncio.sleep(3)

    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        print("Product Service: Redis connected")
    except Exception as e:
        print(f"Product Service: Redis connection failed: {e}")

    yield

    if redis_client:
        await redis_client.close()


app = FastAPI(title="ResilienceOS Product Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(ChaosMiddleware, metrics=metrics)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    category: Optional[str]
    stock_quantity: int

    class Config:
        from_attributes = True


@app.get("/health")
async def health():
    return metrics.to_health_dict()


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    return metrics.to_prometheus_text()


@app.get("/products")
async def list_products(
    skip: int = 0,
    limit: int = 50,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    if category:
        query = query.filter(Product.category == category)
    products = query.offset(skip).limit(limit).all()
    return [ProductResponse.from_orm(p) for p in products]


@app.get("/products/{product_id}")
async def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    # Publish view event to Redis
    if redis_client:
        try:
            event = json.dumps({
                "event": "product_viewed",
                "product_id": product_id,
                "product_name": product.name,
                "timestamp": __import__("time").time()
            })
            await redis_client.publish("product_events", event)
        except Exception:
            pass  # Redis unavailability should not break product reads

    return ProductResponse.from_orm(product)


@app.post("/chaos/configure")
async def configure_chaos(config: dict):
    metrics.chaos_enabled = config.get("enabled", False)
    metrics.chaos_latency_ms = config.get("latency_ms", 0)
    metrics.chaos_error_rate = config.get("error_rate", 0.0)
    metrics.chaos_jitter_ms = config.get("jitter_ms", 0)
    return {"status": "applied", "service": "product-service", "config": config}

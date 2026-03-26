"""
ResilienceOS Notification Service (port 8004)
Consumes Redis pub/sub for order and product events.
Logs notifications to PostgreSQL.
"""
import sys
import os
import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import redis.asyncio as aioredis

sys.path.insert(0, "/app")
from services.shared import ServiceMetrics, ChaosMiddleware, get_db_url, get_redis_url
from postgres.models import Base, NotificationLog

metrics = ServiceMetrics("notification-service")

DATABASE_URL = get_db_url()
REDIS_URL = get_redis_url()

engine = None
SessionLocal = None
redis_client = None
_subscriber_task = None


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


async def process_order_event(data: dict):
    """Simulate sending order confirmation email/SMS."""
    db = SessionLocal()
    try:
        msg = (
            f"Order #{data.get('order_id')} created for user #{data.get('user_id')}. "
            f"Total: ${data.get('total_price', 0):.2f}"
        )
        db.add(NotificationLog(
            service="notification-service",
            event_type="order_confirmation",
            message=msg
        ))
        db.commit()
        print(f"Notification Service: Processed order event - {msg}")
    except Exception as e:
        print(f"Notification Service: Error processing order event: {e}")
        db.rollback()
    finally:
        db.close()


async def process_product_event(data: dict):
    """Log product view events."""
    db = SessionLocal()
    try:
        db.add(NotificationLog(
            service="notification-service",
            event_type="product_view",
            message=f"Product #{data.get('product_id')} '{data.get('product_name')}' viewed"
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def redis_subscriber():
    """Background task: subscribe to Redis channels and process events."""
    global redis_client
    while True:
        try:
            redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("order_events", "product_events")
            print("Notification Service: Redis subscriber active")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    channel = message["channel"]
                    if channel == "order_events":
                        await process_order_event(data)
                    elif channel == "product_events":
                        await process_product_event(data)
                except Exception as e:
                    print(f"Notification Service: Message processing error: {e}")

        except Exception as e:
            print(f"Notification Service: Redis subscriber error: {e}. Retrying in 5s...")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _subscriber_task
    for attempt in range(10):
        try:
            init_db()
            print("Notification Service: DB connected")
            break
        except Exception as e:
            print(f"Notification Service: DB attempt {attempt+1}/10: {e}")
            await asyncio.sleep(3)

    _subscriber_task = asyncio.create_task(redis_subscriber())

    yield

    if _subscriber_task:
        _subscriber_task.cancel()
    if redis_client:
        await redis_client.close()


app = FastAPI(title="ResilienceOS Notification Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(ChaosMiddleware, metrics=metrics)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    h = metrics.to_health_dict()
    redis_ok = False
    try:
        if redis_client:
            await redis_client.ping()
            redis_ok = True
    except Exception:
        pass
    h["redis_connected"] = redis_ok
    return h


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    return metrics.to_prometheus_text()


@app.get("/notifications")
async def list_notifications(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(NotificationLog).order_by(
        NotificationLog.created_at.desc()
    ).limit(limit).all()
    return [
        {
            "id": n.id,
            "service": n.service,
            "event_type": n.event_type,
            "message": n.message,
            "created_at": n.created_at.isoformat()
        }
        for n in logs
    ]


@app.post("/chaos/configure")
async def configure_chaos(config: dict):
    metrics.chaos_enabled = config.get("enabled", False)
    metrics.chaos_latency_ms = config.get("latency_ms", 0)
    metrics.chaos_error_rate = config.get("error_rate", 0.0)
    metrics.chaos_jitter_ms = config.get("jitter_ms", 0)
    return {"status": "applied", "service": "notification-service", "config": config}

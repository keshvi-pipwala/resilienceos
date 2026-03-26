"""
ResilienceOS User Service (port 8001)
Manages user data with PostgreSQL. Demonstrates cascade failure source.
"""
import sys
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

sys.path.insert(0, "/app")
from services.shared import ServiceMetrics, ChaosMiddleware, get_db_url
from postgres.models import Base, User

metrics = ServiceMetrics("user-service")

DATABASE_URL = get_db_url()
engine = None
SessionLocal = None


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
    for attempt in range(10):
        try:
            init_db()
            print("User Service: DB connected")
            break
        except Exception as e:
            print(f"User Service: DB connection attempt {attempt+1}/10 failed: {e}")
            import asyncio
            await asyncio.sleep(3)
    yield


app = FastAPI(title="ResilienceOS User Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(ChaosMiddleware, metrics=metrics)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@app.get("/health")
async def health():
    return metrics.to_health_dict()


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    return metrics.to_prometheus_text()


@app.get("/users")
async def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(User).filter(User.is_active == True).offset(skip).limit(limit).all()
    return [UserResponse.from_orm(u) for u in users]


@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return UserResponse.from_orm(user)


@app.post("/users", status_code=201)
async def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User with this email or username already exists")
    user = User(**user_data.dict())
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.from_orm(user)


@app.post("/chaos/configure")
async def configure_chaos(config: dict):
    metrics.chaos_enabled = config.get("enabled", False)
    metrics.chaos_latency_ms = config.get("latency_ms", 0)
    metrics.chaos_error_rate = config.get("error_rate", 0.0)
    metrics.chaos_jitter_ms = config.get("jitter_ms", 0)
    return {"status": "applied", "service": "user-service", "config": config}

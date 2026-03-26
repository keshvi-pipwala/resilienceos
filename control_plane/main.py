"""
ResilienceOS Control Plane API (port 9000)
REST API and WebSocket server for the React dashboard.
Aggregates health data from all services and manages post-mortems.
"""
import os
import sys
import json
import asyncio
import time
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

sys.path.insert(0, "/app")
from services.shared import get_db_url
from postgres.models import (
    Base, ChaosExperiment, ExperimentMetric, CascadeEvent,
    PostMortem, Service, NotificationLog
)
from control_plane.postmortem import generate_postmortem

DATABASE_URL = get_db_url()

SERVICE_URLS = {
    "api-gateway": os.getenv("API_GATEWAY_URL", "http://api-gateway:8000"),
    "user-service": os.getenv("USER_SERVICE_URL", "http://user-service:8001"),
    "product-service": os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8002"),
    "order-service": os.getenv("ORDER_SERVICE_URL", "http://order-service:8003"),
    "notification-service": os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8004"),
}
CHAOS_AGENT_URL = os.getenv("CHAOS_AGENT_URL", "http://chaos-agent:8010")

engine = None
SessionLocal = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()


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


async def poll_service_health():
    """Background task: poll all services and broadcast via WebSocket."""
    while True:
        try:
            health_data = {}
            async with httpx.AsyncClient(timeout=2.0) as client:
                for name, url in SERVICE_URLS.items():
                    try:
                        resp = await client.get(f"{url}/health")
                        if resp.status_code == 200:
                            health_data[name] = resp.json()
                        else:
                            health_data[name] = {
                                "status": "unhealthy",
                                "error": f"HTTP {resp.status_code}"
                            }
                    except Exception as e:
                        health_data[name] = {
                            "status": "unreachable",
                            "error": str(e)[:100]
                        }

            # Get active chaos
            chaos_active = {}
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{CHAOS_AGENT_URL}/chaos/active")
                    if resp.status_code == 200:
                        chaos_active = resp.json()
            except Exception:
                pass

            payload = {
                "type": "health_update",
                "timestamp": time.time(),
                "services": health_data,
                "chaos": chaos_active
            }
            await manager.broadcast(payload)

        except Exception as e:
            print(f"Control Plane: Health poll error: {e}")

        await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(10):
        try:
            init_db()
            print("Control Plane: DB connected")
            break
        except Exception as e:
            print(f"Control Plane: DB attempt {attempt+1}/10: {e}")
            await asyncio.sleep(3)

    asyncio.create_task(poll_service_health())
    yield


app = FastAPI(title="ResilienceOS Control Plane", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket ---

@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send immediate snapshot on connect
        health_data = {}
        async with httpx.AsyncClient(timeout=2.0) as client:
            for name, url in SERVICE_URLS.items():
                try:
                    resp = await client.get(f"{url}/health")
                    health_data[name] = resp.json() if resp.status_code == 200 else {"status": "unhealthy"}
                except Exception:
                    health_data[name] = {"status": "unreachable"}

        await websocket.send_json({
            "type": "health_update",
            "timestamp": time.time(),
            "services": health_data,
            "chaos": {}
        })

        # Keep connection alive
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "timestamp": time.time()})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- Health ---

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "control-plane"}


# --- Services ---

@app.get("/api/services/health")
async def get_all_health():
    health_data = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in SERVICE_URLS.items():
            try:
                resp = await client.get(f"{url}/health")
                health_data[name] = resp.json() if resp.status_code == 200 else {
                    "status": "unhealthy", "error": f"HTTP {resp.status_code}"
                }
            except Exception as e:
                health_data[name] = {"status": "unreachable", "error": str(e)[:100]}
    return health_data


@app.get("/api/services")
async def get_services(db: Session = Depends(get_db)):
    services = db.query(Service).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "port": s.port,
            "description": s.description,
            "dependencies": s.dependencies
        }
        for s in services
    ]


# --- Chaos ---

@app.post("/api/chaos/latency")
async def inject_latency(payload: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/latency", json=payload)
    return resp.json()


@app.post("/api/chaos/errors")
async def inject_errors(payload: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/errors", json=payload)
    return resp.json()


@app.post("/api/chaos/partition")
async def inject_partition(payload: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/partition", json=payload)
    return resp.json()


@app.post("/api/chaos/resources")
async def inject_resources(payload: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/resources", json=payload)
    return resp.json()


@app.post("/api/chaos/kill")
async def kill_service(payload: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/kill", json=payload)
    return resp.json()


@app.post("/api/chaos/scenario")
async def run_scenario(payload: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/scenario", json=payload)
    return resp.json()


@app.post("/api/chaos/stop-all")
async def stop_all():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CHAOS_AGENT_URL}/chaos/stop-all")
    return resp.json()


@app.get("/api/chaos/active")
async def get_active_chaos():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{CHAOS_AGENT_URL}/chaos/active")
        return resp.json()
    except Exception as e:
        return {"active_experiments": [], "active_faults": {}, "error": str(e)}


@app.get("/api/chaos/experiments")
async def get_experiments(db: Session = Depends(get_db)):
    experiments = db.query(ChaosExperiment).order_by(
        ChaosExperiment.started_at.desc()
    ).limit(50).all()
    return [
        {
            "id": e.id,
            "scenario_name": e.scenario_name,
            "fault_type": e.fault_type,
            "target_service": e.target_service,
            "parameters": e.parameters,
            "started_at": e.started_at.isoformat(),
            "ended_at": e.ended_at.isoformat() if e.ended_at else None,
            "status": e.status,
            "blast_radius_score": e.blast_radius_score,
            "has_post_mortem": e.post_mortem is not None
        }
        for e in experiments
    ]


@app.get("/api/chaos/experiments/{experiment_id}")
async def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    exp = db.query(ChaosExperiment).filter_by(id=experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    metrics = db.query(ExperimentMetric).filter_by(experiment_id=experiment_id).all()
    cascades = db.query(CascadeEvent).filter_by(experiment_id=experiment_id).all()
    return {
        "id": exp.id,
        "scenario_name": exp.scenario_name,
        "fault_type": exp.fault_type,
        "target_service": exp.target_service,
        "parameters": exp.parameters,
        "started_at": exp.started_at.isoformat(),
        "ended_at": exp.ended_at.isoformat() if exp.ended_at else None,
        "status": exp.status,
        "blast_radius_score": exp.blast_radius_score,
        "metrics": [
            {
                "service_name": m.service_name,
                "timestamp": m.timestamp.isoformat(),
                "error_rate": m.error_rate,
                "latency_p99": m.latency_p99,
                "request_rate": m.request_rate,
                "status": m.status
            }
            for m in metrics
        ],
        "cascade_events": [
            {
                "source_service": c.source_service,
                "affected_service": c.affected_service,
                "detected_at": c.detected_at.isoformat(),
                "delay_seconds": c.delay_seconds,
                "impact_description": c.impact_description
            }
            for c in cascades
        ]
    }


# --- Post-Mortems ---

@app.post("/api/postmortems/generate/{experiment_id}")
async def generate_pm(experiment_id: int, db: Session = Depends(get_db)):
    exp = db.query(ChaosExperiment).filter_by(id=experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status == "running":
        raise HTTPException(status_code=400, detail="Cannot generate post-mortem for running experiment")

    asyncio.create_task(_generate_pm_task(experiment_id))
    return {"status": "generating", "experiment_id": experiment_id}


async def _generate_pm_task(experiment_id: int):
    db = SessionLocal()
    try:
        pm = await generate_postmortem(experiment_id, db)
        if pm:
            await manager.broadcast({
                "type": "postmortem_ready",
                "experiment_id": experiment_id,
                "postmortem_id": pm.id
            })
    except Exception as e:
        print(f"Post-mortem generation failed for experiment {experiment_id}: {e}")
    finally:
        db.close()


@app.get("/api/postmortems")
async def list_postmortems(db: Session = Depends(get_db)):
    pms = db.query(PostMortem).order_by(PostMortem.generated_at.desc()).limit(50).all()
    return [
        {
            "id": pm.id,
            "experiment_id": pm.experiment_id,
            "severity": pm.severity,
            "title": pm.title,
            "summary": pm.summary,
            "resilience_score": pm.resilience_score,
            "generated_at": pm.generated_at.isoformat(),
            "services_affected": pm.full_report.get("impact", {}).get("services_affected", [])
        }
        for pm in pms
    ]


@app.get("/api/postmortems/{pm_id}")
async def get_postmortem(pm_id: int, db: Session = Depends(get_db)):
    pm = db.query(PostMortem).filter_by(id=pm_id).first()
    if not pm:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    return {
        "id": pm.id,
        "experiment_id": pm.experiment_id,
        "severity": pm.severity,
        "title": pm.title,
        "summary": pm.summary,
        "full_report": pm.full_report,
        "resilience_score": pm.resilience_score,
        "generated_at": pm.generated_at.isoformat()
    }


# --- Metrics history ---

@app.get("/api/metrics/history/{service_name}")
async def get_metrics_history(service_name: str, limit: int = 100, db: Session = Depends(get_db)):
    metrics = db.query(ExperimentMetric).filter_by(
        service_name=service_name
    ).order_by(ExperimentMetric.timestamp.desc()).limit(limit).all()
    return [
        {
            "timestamp": m.timestamp.isoformat(),
            "error_rate": m.error_rate,
            "latency_p99": m.latency_p99,
            "request_rate": m.request_rate,
            "status": m.status,
            "experiment_id": m.experiment_id
        }
        for m in reversed(metrics)
    ]


@app.get("/api/cascade/events")
async def get_cascade_events(limit: int = 50, db: Session = Depends(get_db)):
    events = db.query(CascadeEvent).order_by(
        CascadeEvent.detected_at.desc()
    ).limit(limit).all()
    return [
        {
            "id": e.id,
            "experiment_id": e.experiment_id,
            "source_service": e.source_service,
            "affected_service": e.affected_service,
            "detected_at": e.detected_at.isoformat(),
            "delay_seconds": e.delay_seconds,
            "impact_description": e.impact_description
        }
        for e in events
    ]

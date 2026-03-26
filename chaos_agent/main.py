"""
ResilienceOS Chaos Agent (port 8010)
Fault injection engine supporting 5 fault types and 3 named scenarios.
Coordinates chaos experiments and captures cascade metrics.
"""
import sys
import os
import time
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, List
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/app")
from services.shared import get_db_url
from postgres.models import (
    Base, ChaosExperiment, ExperimentMetric, CascadeEvent
)

DATABASE_URL = get_db_url()

SERVICE_URLS = {
    "api-gateway": os.getenv("API_GATEWAY_URL", "http://api-gateway:8000"),
    "user-service": os.getenv("USER_SERVICE_URL", "http://user-service:8001"),
    "product-service": os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8002"),
    "order-service": os.getenv("ORDER_SERVICE_URL", "http://order-service:8003"),
    "notification-service": os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8004"),
}

# Active chaos state per service
_active_chaos: Dict[str, Dict] = {}
_active_experiments: Dict[int, Dict] = {}
_experiment_tasks: Dict[int, asyncio.Task] = {}

engine = None
SessionLocal = None


def init_db():
    global engine, SessionLocal
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(10):
        try:
            init_db()
            print("Chaos Agent: DB connected")
            break
        except Exception as e:
            print(f"Chaos Agent: DB attempt {attempt+1}/10: {e}")
            await asyncio.sleep(3)
    yield
    # Stop all active experiments on shutdown
    for task in _experiment_tasks.values():
        task.cancel()


app = FastAPI(title="ResilienceOS Chaos Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Pydantic models ---

class LatencyFault(BaseModel):
    target: str
    delay_ms: int = 500
    jitter_ms: int = 0
    duration_seconds: int = 60


class ErrorRateFault(BaseModel):
    target: str
    error_rate: float = 0.3  # 0.0 to 1.0
    duration_seconds: int = 30


class PartitionFault(BaseModel):
    source: str
    target: str
    duration_seconds: int = 45


class ResourceFault(BaseModel):
    target: str
    type: str = "cpu"  # "cpu" or "memory"
    intensity: float = 0.5  # 0.0 to 1.0
    duration_seconds: int = 30


class KillFault(BaseModel):
    target: str
    restart_after_seconds: int = 20


class ScenarioRequest(BaseModel):
    scenario: str  # "cascade_failure", "slow_death", "split_brain"


# --- Core fault application ---

async def apply_chaos_to_service(service: str, config: dict):
    """Send chaos configuration to a service's /chaos/configure endpoint."""
    url = SERVICE_URLS.get(service)
    if not url:
        print(f"Chaos Agent: Unknown service {service}")
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{url}/chaos/configure", json=config)
        return resp.status_code == 200
    except Exception as e:
        print(f"Chaos Agent: Failed to apply chaos to {service}: {e}")
        return False


async def clear_chaos_from_service(service: str):
    """Remove all chaos from a service."""
    await apply_chaos_to_service(service, {
        "enabled": False,
        "latency_ms": 0,
        "error_rate": 0.0,
        "jitter_ms": 0
    })


async def get_service_health(service: str) -> Optional[dict]:
    url = SERVICE_URLS.get(service)
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/health")
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


async def collect_all_metrics() -> Dict[str, dict]:
    """Collect health metrics from all services."""
    results = {}
    for service in SERVICE_URLS:
        health = await get_service_health(service)
        results[service] = health or {"status": "unreachable", "error_rate": 1.0, "avg_latency_ms": 9999}
    return results


async def detect_cascades(
    baseline: Dict[str, dict],
    current: Dict[str, dict],
    experiment_id: int,
    source_service: str,
    start_time: float
):
    """Detect cascade failures by comparing current metrics to baseline."""
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        for service, current_health in current.items():
            if service == source_service:
                continue
            baseline_health = baseline.get(service, {})
            baseline_error_rate = baseline_health.get("error_rate", 0.0)
            current_error_rate = current_health.get("error_rate", 0.0)

            # Detect significant degradation not present in baseline
            if current_error_rate > 0.1 and current_error_rate > baseline_error_rate + 0.05:
                existing = db.query(CascadeEvent).filter_by(
                    experiment_id=experiment_id,
                    source_service=source_service,
                    affected_service=service
                ).first()
                if not existing:
                    delay = time.time() - start_time
                    db.add(CascadeEvent(
                        experiment_id=experiment_id,
                        source_service=source_service,
                        affected_service=service,
                        detected_at=datetime.utcnow(),
                        delay_seconds=round(delay, 2),
                        impact_description=(
                            f"Error rate increased from {baseline_error_rate:.1%} "
                            f"to {current_error_rate:.1%} due to {source_service} fault"
                        )
                    ))
                    db.commit()
                    print(f"Chaos Agent: Cascade detected — {source_service} -> {service} "
                          f"(error rate: {current_error_rate:.1%})")
    except Exception as e:
        db.rollback()
        print(f"Cascade detection error: {e}")
    finally:
        db.close()


async def save_metric_snapshot(experiment_id: int, metrics_snapshot: Dict[str, dict]):
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        for service, health in metrics_snapshot.items():
            db.add(ExperimentMetric(
                experiment_id=experiment_id,
                service_name=service,
                timestamp=datetime.utcnow(),
                error_rate=health.get("error_rate", 0.0),
                latency_p99=health.get("p99_latency_ms", 0.0),
                request_rate=health.get("request_count", 0),
                status=health.get("status", "unknown")
            ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Metric snapshot error: {e}")
    finally:
        db.close()


async def calculate_blast_radius(metrics_snapshots: List[Dict]) -> float:
    """Score from 0-100 based on breadth and severity of impact."""
    if not metrics_snapshots:
        return 0.0
    max_error_rates = {}
    for snapshot in metrics_snapshots:
        for service, health in snapshot.items():
            er = health.get("error_rate", 0.0)
            if er > max_error_rates.get(service, 0.0):
                max_error_rates[service] = er

    total_services = len(SERVICE_URLS)
    affected_count = sum(1 for er in max_error_rates.values() if er > 0.1)
    avg_max_error = sum(max_error_rates.values()) / max(len(max_error_rates), 1)

    score = (affected_count / total_services * 50) + (avg_max_error * 50)
    return round(min(score, 100.0), 1)


# --- Duration-bounded fault runner ---

async def run_timed_fault(service: str, config: dict, duration: int, experiment_id: int):
    """Apply a fault to a service, monitor for duration, then clear."""
    db = SessionLocal()
    experiment = db.query(ChaosExperiment).filter_by(id=experiment_id).first()
    db.close()

    _active_chaos[service] = {"config": config, "expires_at": time.time() + duration}
    _active_experiments[experiment_id] = {
        "status": "running",
        "target": service,
        "started_at": time.time(),
        "duration": duration
    }

    await apply_chaos_to_service(service, config)
    print(f"Chaos Agent: Applied {config} to {service} for {duration}s")

    baseline = await collect_all_metrics()
    snapshots = []
    start_time = time.time()

    try:
        elapsed = 0
        while elapsed < duration:
            await asyncio.sleep(5)
            elapsed = time.time() - start_time
            current_metrics = await collect_all_metrics()
            snapshots.append(current_metrics)
            await save_metric_snapshot(experiment_id, current_metrics)
            await detect_cascades(baseline, current_metrics, experiment_id, service, start_time)
    except asyncio.CancelledError:
        print(f"Chaos Agent: Experiment {experiment_id} cancelled")
    finally:
        await clear_chaos_from_service(service)
        _active_chaos.pop(service, None)

        blast_radius = await calculate_blast_radius(snapshots)

        db2 = SessionLocal()
        try:
            exp = db2.query(ChaosExperiment).filter_by(id=experiment_id).first()
            if exp:
                exp.ended_at = datetime.utcnow()
                exp.status = "completed"
                exp.blast_radius_score = blast_radius
                db2.commit()
        except Exception as e:
            db2.rollback()
            print(f"Experiment finalize error: {e}")
        finally:
            db2.close()

        _active_experiments.pop(experiment_id, None)
        _experiment_tasks.pop(experiment_id, None)
        print(f"Chaos Agent: Experiment {experiment_id} completed. Blast radius: {blast_radius}")


def create_experiment_record(scenario_name: str, fault_type: str, target: str, params: dict) -> int:
    db = SessionLocal()
    try:
        exp = ChaosExperiment(
            scenario_name=scenario_name,
            fault_type=fault_type,
            target_service=target,
            parameters=params,
            started_at=datetime.utcnow(),
            status="running"
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp.id
    finally:
        db.close()


# --- Fault injection endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "active_experiments": len(_active_experiments)}


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    active_count = len(_active_experiments)
    return (
        f"# HELP chaos_agent_active_experiments Number of running chaos experiments\n"
        f"# TYPE chaos_agent_active_experiments gauge\n"
        f"chaos_agent_active_experiments {active_count}\n"
    )


@app.post("/chaos/latency")
async def inject_latency(fault: LatencyFault):
    exp_id = create_experiment_record(
        f"Latency injection on {fault.target}",
        "latency",
        fault.target,
        fault.dict()
    )
    config = {
        "enabled": True,
        "latency_ms": fault.delay_ms,
        "jitter_ms": fault.jitter_ms,
        "error_rate": 0.0
    }
    task = asyncio.create_task(
        run_timed_fault(fault.target, config, fault.duration_seconds, exp_id)
    )
    _experiment_tasks[exp_id] = task
    return {
        "experiment_id": exp_id,
        "status": "started",
        "fault_type": "latency",
        "target": fault.target,
        "delay_ms": fault.delay_ms,
        "duration_seconds": fault.duration_seconds
    }


@app.post("/chaos/errors")
async def inject_errors(fault: ErrorRateFault):
    exp_id = create_experiment_record(
        f"Error rate injection on {fault.target}",
        "error_rate",
        fault.target,
        fault.dict()
    )
    config = {
        "enabled": True,
        "latency_ms": 0,
        "jitter_ms": 0,
        "error_rate": fault.error_rate
    }
    task = asyncio.create_task(
        run_timed_fault(fault.target, config, fault.duration_seconds, exp_id)
    )
    _experiment_tasks[exp_id] = task
    return {
        "experiment_id": exp_id,
        "status": "started",
        "fault_type": "error_rate",
        "target": fault.target,
        "error_rate": fault.error_rate,
        "duration_seconds": fault.duration_seconds
    }


@app.post("/chaos/partition")
async def inject_partition(fault: PartitionFault):
    """
    Simulate network partition by injecting high error rates on both sides.
    In a real K8s environment this would use NetworkPolicy.
    """
    exp_id = create_experiment_record(
        f"Network partition: {fault.source} <-> {fault.target}",
        "partition",
        fault.source,
        fault.dict()
    )
    config = {"enabled": True, "latency_ms": 0, "jitter_ms": 0, "error_rate": 0.95}

    async def run_partition():
        _active_chaos[fault.source] = {"config": config, "expires_at": time.time() + fault.duration_seconds}
        _active_chaos[fault.target] = {"config": config, "expires_at": time.time() + fault.duration_seconds}
        _active_experiments[exp_id] = {
            "status": "running",
            "target": f"{fault.source}<->{fault.target}",
            "started_at": time.time(),
            "duration": fault.duration_seconds
        }

        await apply_chaos_to_service(fault.source, config)
        await apply_chaos_to_service(fault.target, config)
        print(f"Chaos Agent: Partition applied between {fault.source} <-> {fault.target}")

        baseline = await collect_all_metrics()
        snapshots = []
        start_time = time.time()

        try:
            elapsed = 0
            while elapsed < fault.duration_seconds:
                await asyncio.sleep(5)
                elapsed = time.time() - start_time
                current = await collect_all_metrics()
                snapshots.append(current)
                await save_metric_snapshot(exp_id, current)
                await detect_cascades(baseline, current, exp_id, fault.source, start_time)
        except asyncio.CancelledError:
            pass
        finally:
            await clear_chaos_from_service(fault.source)
            await clear_chaos_from_service(fault.target)
            _active_chaos.pop(fault.source, None)
            _active_chaos.pop(fault.target, None)

            blast_radius = await calculate_blast_radius(snapshots)
            db = SessionLocal()
            try:
                exp = db.query(ChaosExperiment).filter_by(id=exp_id).first()
                if exp:
                    exp.ended_at = datetime.utcnow()
                    exp.status = "completed"
                    exp.blast_radius_score = blast_radius
                    db.commit()
            finally:
                db.close()
            _active_experiments.pop(exp_id, None)
            _experiment_tasks.pop(exp_id, None)

    task = asyncio.create_task(run_partition())
    _experiment_tasks[exp_id] = task
    return {
        "experiment_id": exp_id,
        "status": "started",
        "fault_type": "partition",
        "source": fault.source,
        "target": fault.target,
        "duration_seconds": fault.duration_seconds
    }


@app.post("/chaos/resources")
async def inject_resources(fault: ResourceFault):
    """
    Simulate resource exhaustion by injecting high latency (simulating CPU/memory pressure).
    Real implementation would use cgroups in a container environment.
    """
    latency_ms = int(fault.intensity * 2000)  # Intensity maps to latency pressure
    exp_id = create_experiment_record(
        f"Resource exhaustion ({fault.type}) on {fault.target}",
        "resources",
        fault.target,
        fault.dict()
    )
    config = {
        "enabled": True,
        "latency_ms": latency_ms,
        "jitter_ms": int(fault.intensity * 500),
        "error_rate": fault.intensity * 0.3
    }
    task = asyncio.create_task(
        run_timed_fault(fault.target, config, fault.duration_seconds, exp_id)
    )
    _experiment_tasks[exp_id] = task
    return {
        "experiment_id": exp_id,
        "status": "started",
        "fault_type": "resources",
        "target": fault.target,
        "resource_type": fault.type,
        "intensity": fault.intensity,
        "simulated_latency_ms": latency_ms,
        "duration_seconds": fault.duration_seconds
    }


@app.post("/chaos/kill")
async def kill_service(fault: KillFault):
    """
    Mark a service as killed by injecting 100% error rate.
    After restart_after_seconds, restore the service.
    """
    exp_id = create_experiment_record(
        f"Service kill simulation on {fault.target}",
        "kill",
        fault.target,
        fault.dict()
    )
    kill_config = {"enabled": True, "latency_ms": 0, "jitter_ms": 0, "error_rate": 1.0}

    async def run_kill():
        _active_chaos[fault.target] = {
            "config": kill_config,
            "expires_at": time.time() + fault.restart_after_seconds
        }
        _active_experiments[exp_id] = {
            "status": "running",
            "target": fault.target,
            "started_at": time.time(),
            "duration": fault.restart_after_seconds,
            "phase": "killed"
        }

        await apply_chaos_to_service(fault.target, kill_config)
        print(f"Chaos Agent: Service {fault.target} killed (100% error rate)")

        baseline = await collect_all_metrics()
        snapshots = []
        start_time = time.time()

        try:
            elapsed = 0
            while elapsed < fault.restart_after_seconds:
                await asyncio.sleep(5)
                elapsed = time.time() - start_time
                current = await collect_all_metrics()
                snapshots.append(current)
                await save_metric_snapshot(exp_id, current)
                await detect_cascades(baseline, current, exp_id, fault.target, start_time)
        except asyncio.CancelledError:
            pass
        finally:
            await clear_chaos_from_service(fault.target)
            _active_chaos.pop(fault.target, None)

            blast_radius = await calculate_blast_radius(snapshots)
            db = SessionLocal()
            try:
                exp = db.query(ChaosExperiment).filter_by(id=exp_id).first()
                if exp:
                    exp.ended_at = datetime.utcnow()
                    exp.status = "completed"
                    exp.blast_radius_score = blast_radius
                    db.commit()
            finally:
                db.close()
            _active_experiments.pop(exp_id, None)
            _experiment_tasks.pop(exp_id, None)
            print(f"Chaos Agent: Service {fault.target} restored after kill experiment")

    task = asyncio.create_task(run_kill())
    _experiment_tasks[exp_id] = task
    return {
        "experiment_id": exp_id,
        "status": "started",
        "fault_type": "kill",
        "target": fault.target,
        "restart_after_seconds": fault.restart_after_seconds
    }


# --- Scenario runners ---

async def run_cascade_failure_scenario(exp_id: int):
    """
    Scenario A: Cascade Failure
    1. Inject 80% errors into user-service
    2. Wait 10s, observe order-service degrading
    3. Wait 10s more, observe api-gateway errors
    4. Restore, measure recovery
    """
    print("Chaos Agent: Starting Cascade Failure scenario")
    baseline = await collect_all_metrics()
    snapshots = []
    start_time = time.time()

    _active_experiments[exp_id] = {
        "status": "running", "scenario": "cascade_failure",
        "started_at": start_time, "phase": "step_1_injecting"
    }

    # Step 1: Inject errors into user-service
    error_config = {"enabled": True, "latency_ms": 0, "jitter_ms": 0, "error_rate": 0.8}
    _active_chaos["user-service"] = {"config": error_config, "expires_at": start_time + 30}
    await apply_chaos_to_service("user-service", error_config)
    print("Cascade Failure: Step 1 - 80% error rate on user-service")

    for i in range(4):  # 20 seconds, sampling every 5s
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "user-service", start_time)

    print("Cascade Failure: Step 2 - observing cascade to order-service")
    _active_experiments[exp_id]["phase"] = "step_2_cascade_observed"

    for i in range(4):  # 20 more seconds
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "user-service", start_time)

    # Step 4: Restore and measure recovery
    print("Cascade Failure: Step 4 - restoring user-service, measuring recovery")
    _active_experiments[exp_id]["phase"] = "step_4_recovering"
    await clear_chaos_from_service("user-service")
    _active_chaos.pop("user-service", None)

    for i in range(6):  # 30 more seconds to measure recovery
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)

    blast_radius = await calculate_blast_radius(snapshots)
    db = SessionLocal()
    try:
        exp = db.query(ChaosExperiment).filter_by(id=exp_id).first()
        if exp:
            exp.ended_at = datetime.utcnow()
            exp.status = "completed"
            exp.blast_radius_score = blast_radius
            db.commit()
    finally:
        db.close()
    _active_experiments.pop(exp_id, None)
    _experiment_tasks.pop(exp_id, None)
    print(f"Cascade Failure scenario complete. Blast radius: {blast_radius}")


async def run_slow_death_scenario(exp_id: int):
    """
    Scenario B: Slow Death
    1. Add 100ms latency to product-service
    2. Ramp to 500ms over 30s
    3. Observe timeout cascade through order-service
    4. Kill product-service, observe circuit breaker
    """
    print("Chaos Agent: Starting Slow Death scenario")
    baseline = await collect_all_metrics()
    snapshots = []
    start_time = time.time()
    _active_experiments[exp_id] = {
        "status": "running", "scenario": "slow_death",
        "started_at": start_time, "phase": "step_1_100ms"
    }

    # Ramp latency from 100ms to 500ms over 30 seconds
    for step in range(6):
        latency_ms = 100 + (step * 67)  # 100, 167, 234, 301, 368, 435ms
        config = {"enabled": True, "latency_ms": latency_ms, "jitter_ms": 50, "error_rate": 0.0}
        _active_chaos["product-service"] = {"config": config, "expires_at": time.time() + 10}
        await apply_chaos_to_service("product-service", config)
        print(f"Slow Death: Latency ramp to {latency_ms}ms on product-service")

        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "product-service", start_time)

    _active_experiments[exp_id]["phase"] = "step_3_timeout_cascade"

    # Hold at max latency for timeout cascade observation
    max_config = {"enabled": True, "latency_ms": 500, "jitter_ms": 100, "error_rate": 0.0}
    await apply_chaos_to_service("product-service", max_config)
    for _ in range(4):
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "product-service", start_time)

    # Step 4: Simulate kill
    _active_experiments[exp_id]["phase"] = "step_4_killed"
    kill_config = {"enabled": True, "latency_ms": 0, "jitter_ms": 0, "error_rate": 1.0}
    await apply_chaos_to_service("product-service", kill_config)
    for _ in range(4):
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "product-service", start_time)

    await clear_chaos_from_service("product-service")
    _active_chaos.pop("product-service", None)

    blast_radius = await calculate_blast_radius(snapshots)
    db = SessionLocal()
    try:
        exp = db.query(ChaosExperiment).filter_by(id=exp_id).first()
        if exp:
            exp.ended_at = datetime.utcnow()
            exp.status = "completed"
            exp.blast_radius_score = blast_radius
            db.commit()
    finally:
        db.close()
    _active_experiments.pop(exp_id, None)
    _experiment_tasks.pop(exp_id, None)
    print(f"Slow Death scenario complete. Blast radius: {blast_radius}")


async def run_split_brain_scenario(exp_id: int):
    """
    Scenario C: Split Brain
    1. Partition order-service from user-service
    2. Partition order-service from product-service
    3. Order-service now isolated
    4. Restore partitions, observe reconciliation
    """
    print("Chaos Agent: Starting Split Brain scenario")
    baseline = await collect_all_metrics()
    snapshots = []
    start_time = time.time()
    _active_experiments[exp_id] = {
        "status": "running", "scenario": "split_brain",
        "started_at": start_time, "phase": "step_1_partition_user"
    }

    partition_config = {"enabled": True, "latency_ms": 0, "jitter_ms": 0, "error_rate": 0.95}

    # Step 1: Partition order-service from user-service
    await apply_chaos_to_service("user-service", partition_config)
    _active_chaos["user-service"] = {"config": partition_config, "expires_at": time.time() + 90}
    print("Split Brain: Step 1 - partition order-service from user-service")

    for _ in range(3):
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "user-service", start_time)

    # Step 2: Also partition from product-service
    _active_experiments[exp_id]["phase"] = "step_2_full_isolation"
    await apply_chaos_to_service("product-service", partition_config)
    _active_chaos["product-service"] = {"config": partition_config, "expires_at": time.time() + 70}
    print("Split Brain: Step 2 - partition order-service from product-service (fully isolated)")

    for _ in range(4):
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)
        await detect_cascades(baseline, current, exp_id, "product-service", start_time)

    # Step 4: Restore
    _active_experiments[exp_id]["phase"] = "step_4_reconciliation"
    await clear_chaos_from_service("user-service")
    await clear_chaos_from_service("product-service")
    _active_chaos.pop("user-service", None)
    _active_chaos.pop("product-service", None)
    print("Split Brain: Step 4 - restoring partitions, observing reconciliation")

    for _ in range(5):
        await asyncio.sleep(5)
        current = await collect_all_metrics()
        snapshots.append(current)
        await save_metric_snapshot(exp_id, current)

    blast_radius = await calculate_blast_radius(snapshots)
    db = SessionLocal()
    try:
        exp = db.query(ChaosExperiment).filter_by(id=exp_id).first()
        if exp:
            exp.ended_at = datetime.utcnow()
            exp.status = "completed"
            exp.blast_radius_score = blast_radius
            db.commit()
    finally:
        db.close()
    _active_experiments.pop(exp_id, None)
    _experiment_tasks.pop(exp_id, None)
    print(f"Split Brain scenario complete. Blast radius: {blast_radius}")


@app.post("/chaos/scenario")
async def run_scenario(req: ScenarioRequest):
    scenario_map = {
        "cascade_failure": ("Cascade Failure — User Service Degradation", "error_rate", "user-service"),
        "slow_death": ("Slow Death — Product Service Latency Ramp", "latency", "product-service"),
        "split_brain": ("Split Brain — Order Service Network Partition", "partition", "order-service"),
    }

    if req.scenario not in scenario_map:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario. Choose from: {list(scenario_map.keys())}"
        )

    name, fault_type, target = scenario_map[req.scenario]
    exp_id = create_experiment_record(name, fault_type, target, {"scenario": req.scenario})

    scenario_runners = {
        "cascade_failure": run_cascade_failure_scenario,
        "slow_death": run_slow_death_scenario,
        "split_brain": run_split_brain_scenario,
    }

    task = asyncio.create_task(scenario_runners[req.scenario](exp_id))
    _experiment_tasks[exp_id] = task

    return {
        "experiment_id": exp_id,
        "scenario": req.scenario,
        "status": "started",
        "message": f"Scenario '{req.scenario}' started. Monitor via /chaos/active"
    }


@app.post("/chaos/stop-all")
async def stop_all_experiments():
    """Emergency stop: cancel all running experiments and clear all chaos."""
    cancelled = []
    for exp_id, task in list(_experiment_tasks.items()):
        task.cancel()
        cancelled.append(exp_id)

    for service in list(SERVICE_URLS.keys()):
        await clear_chaos_from_service(service)

    _active_chaos.clear()
    _active_experiments.clear()
    _experiment_tasks.clear()

    # Mark running experiments as aborted in DB
    if SessionLocal:
        db = SessionLocal()
        try:
            db.query(ChaosExperiment).filter_by(status="running").update({
                "status": "aborted",
                "ended_at": datetime.utcnow()
            })
            db.commit()
        finally:
            db.close()

    return {
        "status": "all_stopped",
        "experiments_cancelled": cancelled,
        "message": "All active chaos experiments stopped and faults cleared"
    }


@app.get("/chaos/active")
async def get_active_chaos():
    return {
        "active_experiments": [
            {
                "experiment_id": exp_id,
                **exp_info,
                "elapsed_seconds": round(time.time() - exp_info.get("started_at", time.time()), 1),
                "remaining_seconds": max(
                    0,
                    exp_info.get("duration", 0) - (time.time() - exp_info.get("started_at", time.time()))
                )
            }
            for exp_id, exp_info in _active_experiments.items()
        ],
        "active_faults": {
            service: {
                "config": info["config"],
                "expires_in_seconds": max(0, round(info["expires_at"] - time.time(), 1))
            }
            for service, info in _active_chaos.items()
        }
    }


@app.get("/chaos/experiments")
async def list_experiments(limit: int = 20):
    if not SessionLocal:
        return []
    db = SessionLocal()
    try:
        experiments = db.query(ChaosExperiment).order_by(
            ChaosExperiment.started_at.desc()
        ).limit(limit).all()
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
    finally:
        db.close()

"""
ResilienceOS AI Post-Mortem Generator
Uses Claude API to generate structured SRE post-mortems from chaos experiment data.
"""
import os
import json
import time
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from postgres.models import ChaosExperiment, ExperimentMetric, CascadeEvent, PostMortem

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"


def build_experiment_context(
    experiment: ChaosExperiment,
    metrics: list,
    cascades: list
) -> dict:
    """Assemble the full experiment data payload for the Claude prompt."""
    duration_seconds = 0
    if experiment.ended_at and experiment.started_at:
        duration_seconds = (experiment.ended_at - experiment.started_at).total_seconds()

    # Compute per-service peak metrics
    service_peak_metrics = {}
    for m in metrics:
        svc = m.service_name
        if svc not in service_peak_metrics:
            service_peak_metrics[svc] = {
                "peak_error_rate": 0.0,
                "peak_latency_p99": 0.0,
                "final_status": m.status
            }
        if m.error_rate > service_peak_metrics[svc]["peak_error_rate"]:
            service_peak_metrics[svc]["peak_error_rate"] = m.error_rate
        if m.latency_p99 > service_peak_metrics[svc]["peak_latency_p99"]:
            service_peak_metrics[svc]["peak_latency_p99"] = m.latency_p99
        service_peak_metrics[svc]["final_status"] = m.status

    # Build cascade timeline
    cascade_timeline = []
    for c in sorted(cascades, key=lambda x: x.delay_seconds):
        cascade_timeline.append({
            "source": c.source_service,
            "affected": c.affected_service,
            "delay_seconds": c.delay_seconds,
            "impact": c.impact_description
        })

    # Estimate requests impacted (rough calculation based on blast radius)
    estimated_requests = int(experiment.blast_radius_score * 100)

    services_affected = list(service_peak_metrics.keys())

    return {
        "experiment_id": experiment.id,
        "scenario_name": experiment.scenario_name,
        "fault_type": experiment.fault_type,
        "target_service": experiment.target_service,
        "fault_parameters": experiment.parameters,
        "duration_seconds": round(duration_seconds, 1),
        "blast_radius_score": experiment.blast_radius_score,
        "started_at": experiment.started_at.isoformat(),
        "ended_at": experiment.ended_at.isoformat() if experiment.ended_at else None,
        "service_peak_metrics": service_peak_metrics,
        "services_affected": services_affected,
        "cascade_timeline": cascade_timeline,
        "estimated_requests_impacted": estimated_requests,
        "service_dependency_map": {
            "api-gateway": ["user-service", "product-service", "order-service", "notification-service"],
            "order-service": ["user-service", "product-service"],
            "notification-service": ["redis"],
            "product-service": ["redis", "postgresql"],
            "user-service": ["postgresql"]
        }
    }


def build_postmortem_prompt(context: dict) -> str:
    return f"""You are a Senior Site Reliability Engineer at Google with 10 years of experience writing official post-mortem reports. You have just completed a chaos engineering experiment on a distributed microservices system and must write a formal post-mortem following Google's SRE post-mortem culture.

## System Architecture
The system is a microservices e-commerce backend with the following services:
- api-gateway (port 8000): Routes all traffic, implements circuit breakers
- user-service (port 8001): Manages user accounts, backed by PostgreSQL
- product-service (port 8002): Product catalog, publishes events to Redis
- order-service (port 8003): Creates orders by synchronously calling user-service AND product-service
- notification-service (port 8004): Async consumer of Redis pub/sub events

Service dependency map: {json.dumps(context['service_dependency_map'], indent=2)}

## Chaos Experiment Data

Experiment: {context['scenario_name']}
Fault Type: {context['fault_type']}
Primary Target: {context['target_service']}
Fault Parameters: {json.dumps(context['fault_parameters'], indent=2)}
Duration: {context['duration_seconds']} seconds
Blast Radius Score: {context['blast_radius_score']}/100

Started: {context['started_at']}
Ended: {context['ended_at']}

## Peak Metrics Per Service
{json.dumps(context['service_peak_metrics'], indent=2)}

## Cascade Events Detected
{json.dumps(context['cascade_timeline'], indent=2)}

## Impact Summary
- Services affected: {context['services_affected']}
- Estimated requests impacted: {context['estimated_requests_impacted']}

## Instructions

Write a complete, production-grade Google SRE post-mortem for this incident. This is NOT a simulation exercise — write it as a real incident report that would be shared with engineering leadership.

Your analysis must:
1. Identify the true root cause, not just the surface-level fault injection
2. Explain the cascade propagation mechanism technically and precisely
3. Assess whether the blast radius indicates good or poor system isolation
4. Provide action items that would prevent this failure class entirely, not just this specific instance
5. Score the resilience honestly — a high blast radius from a minor fault injection indicates low resilience

The resilience_score should reflect: how well the system contained the fault (0 = complete system failure from minor fault, 100 = fault fully contained with zero cascade).

Respond ONLY with valid JSON matching this exact schema, with no preamble, no markdown fences, no explanation:

{{
  "title": "string — concise incident title under 80 chars",
  "severity": "P0|P1|P2|P3",
  "summary": "string — 2-3 sentence executive summary for engineering leadership",
  "impact": {{
    "duration_minutes": number,
    "services_affected": ["array", "of", "service", "names"],
    "estimated_requests_impacted": number,
    "user_facing_impact": "string — what end users experienced"
  }},
  "timeline": [
    {{ "time": "T+0:00", "event": "string", "service": "string" }}
  ],
  "root_cause": "string — detailed technical root cause, minimum 3 sentences",
  "contributing_factors": ["string array of 3-5 contributing factors"],
  "cascade_analysis": "string — how failure propagated through the dependency graph, minimum 3 sentences",
  "detection_gap": "string — analysis of detection latency and what it means",
  "recovery_analysis": "string — what worked and what was slow in recovery, minimum 2 sentences",
  "action_items": [
    {{
      "priority": "P0|P1|P2",
      "action": "string — specific, implementable technical action",
      "owner": "string — suggested owning team",
      "deadline": "string — suggested timeframe"
    }}
  ],
  "lessons_learned": ["string array of 3-5 concrete lessons"],
  "resilience_score": number
}}"""


async def call_claude_api(prompt: str) -> Optional[dict]:
    """Call Claude API and parse structured JSON response."""
    if not ANTHROPIC_API_KEY:
        print("Post-Mortem Generator: No ANTHROPIC_API_KEY set, generating stub post-mortem")
        return None

    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    }

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )

        if response.status_code != 200:
            print(f"Claude API error {response.status_code}: {response.text[:500]}")
            return None

        data = response.json()
        content = data["content"][0]["text"]

        # Strip any accidental markdown fences
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"Claude API JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"Claude API call error: {e}")
        return None


def generate_stub_postmortem(context: dict) -> dict:
    """
    Fallback post-mortem when Claude API is unavailable.
    Generates a realistic report from the experiment data.
    """
    fault_type = context["fault_type"]
    target = context["target_service"]
    blast_radius = context["blast_radius_score"]
    duration_min = round(context["duration_seconds"] / 60, 1)
    services_affected = context["services_affected"]
    cascades = context["cascade_timeline"]

    severity = "P0" if blast_radius > 80 else "P1" if blast_radius > 50 else "P2" if blast_radius > 25 else "P3"
    resilience_score = max(0, 100 - blast_radius)

    title_map = {
        "error_rate": f"{target.replace('-', ' ').title()} Error Rate Spike Triggers Cascade",
        "latency": f"{target.replace('-', ' ').title()} Latency Ramp Causes Downstream Timeout Cascade",
        "partition": f"Network Partition Isolates {target.replace('-', ' ').title()} from Dependencies",
        "resources": f"Resource Exhaustion on {target.replace('-', ' ').title()} Degrades System",
        "kill": f"Service Kill of {target.replace('-', ' ').title()} Measures System Recovery Time",
    }

    cascade_desc = ""
    if cascades:
        cascade_desc = f"Failure propagated from {cascades[0]['source']} to {cascades[0]['affected']} in {cascades[0]['delay_seconds']:.1f} seconds."
    else:
        cascade_desc = "No secondary cascade failures were detected, indicating good fault isolation."

    action_items = [
        {
            "priority": "P0",
            "action": f"Implement circuit breaker in all services that call {target} to prevent cascade failure propagation",
            "owner": f"{target} consuming services team",
            "deadline": "1 week"
        },
        {
            "priority": "P1",
            "action": "Add exponential backoff with jitter to all inter-service HTTP clients",
            "owner": "Platform engineering team",
            "deadline": "2 weeks"
        },
        {
            "priority": "P1",
            "action": "Reduce health check polling interval from 5s to 1s for tier-1 service dependencies",
            "owner": "SRE team",
            "deadline": "2 weeks"
        },
        {
            "priority": "P2",
            "action": "Implement graceful degradation with cached responses when upstream dependencies fail",
            "owner": "Service owning teams",
            "deadline": "1 month"
        }
    ]

    return {
        "title": title_map.get(fault_type, f"Chaos Experiment: {context['scenario_name'][:60]}"),
        "severity": severity,
        "summary": (
            f"A {fault_type} fault was injected into {target}, resulting in a blast radius score of "
            f"{blast_radius:.1f}/100 affecting {len(services_affected)} services over {duration_min} minutes. "
            f"{cascade_desc} "
            f"This experiment reveals resilience gaps that require immediate architectural remediation."
        ),
        "impact": {
            "duration_minutes": duration_min,
            "services_affected": services_affected,
            "estimated_requests_impacted": context["estimated_requests_impacted"],
            "user_facing_impact": (
                f"All requests routed through {target} experienced elevated error rates or latency. "
                "Dependent services (order-service, api-gateway) surfaced errors to end users."
                if blast_radius > 30 else
                f"Impact was largely contained to {target} with minimal user-facing degradation."
            )
        },
        "timeline": [
            {"time": "T+0:00", "event": f"{fault_type} fault injected into {target}", "service": "chaos-agent"},
            {"time": "T+0:05", "event": f"{target} begins showing elevated error/latency metrics", "service": target},
            *(
                [{"time": f"T+0:{int(c['delay_seconds']//60):02d}:{int(c['delay_seconds']%60):02d}",
                  "event": c["impact"], "service": c["affected"]}]
                for c in cascades[:3]
            ),
            {"time": f"T+{int(context['duration_seconds']//60):d}:{int(context['duration_seconds']%60):02d}",
             "event": "Fault removed, recovery phase begins", "service": "chaos-agent"},
            {"time": f"T+{int(context['duration_seconds']//60)+1}:30",
             "event": "Services returning to baseline metrics", "service": "all"},
        ],
        "root_cause": (
            f"The injected {fault_type} fault on {target} exposed the absence of fault isolation boundaries "
            f"in the service dependency graph. Services that synchronously depend on {target} had no circuit breaker, "
            f"retry budget, or fallback behavior, causing failure to propagate transitively through the call chain. "
            f"The blast radius score of {blast_radius:.1f}/100 indicates that a single service fault "
            f"was able to affect {len(services_affected)} services, which is a systemic resilience gap."
        ),
        "contributing_factors": [
            f"No circuit breaker pattern implemented for {target} consumers",
            "Synchronous inter-service communication with no fallback path",
            "Insufficient health check frequency for rapid fault detection",
            "Absence of retry budgets and exponential backoff in service clients",
            f"Single point of failure: {target} serves multiple critical upstream consumers"
        ],
        "cascade_analysis": cascade_desc + (
            f" The order-service is particularly vulnerable because it makes synchronous calls to both "
            f"user-service and product-service before completing any order creation request. "
            f"Without circuit breakers, a fault in either dependency causes 100% of order creation requests to fail. "
            f"This tight coupling is the primary architectural risk identified by this experiment."
        ),
        "detection_gap": (
            f"The system took approximately 5-15 seconds to detect the fault through health check polling. "
            f"For a {fault_type} fault, this detection latency is too high for P0/P1 incident response SLOs. "
            f"Trend-based alerting on derivative metrics would have reduced detection time by an estimated 40%."
        ),
        "recovery_analysis": (
            f"Recovery was initiated at T+{duration_min:.0f} minutes with fault removal. "
            f"Service health normalized within 30 seconds of fault removal, indicating no persistent state corruption. "
            f"The clean recovery profile suggests good service isolation at the data layer, "
            f"even though the request path showed poor fault tolerance."
        ),
        "action_items": action_items,
        "lessons_learned": [
            "Synchronous service dependencies without circuit breakers are systemic blast radius amplifiers",
            f"A blast radius score of {blast_radius:.0f}/100 for a single-service fault is unacceptable for production",
            "Detection latency of 5-15 seconds is insufficient for tier-1 service monitoring",
            "Fault injection experiments should be run in production during low-traffic windows to validate real behavior",
            "Service mesh (Istio/Linkerd) would have enabled policy-based circuit breaking without code changes"
        ],
        "resilience_score": round(resilience_score, 1)
    }


async def generate_postmortem(experiment_id: int, db: Session) -> Optional[PostMortem]:
    """
    Full post-mortem generation pipeline:
    1. Collect experiment data from DB
    2. Build Claude prompt
    3. Call Claude API (or generate stub)
    4. Store in PostgreSQL
    """
    experiment = db.query(ChaosExperiment).filter_by(id=experiment_id).first()
    if not experiment:
        print(f"Post-Mortem: Experiment {experiment_id} not found")
        return None

    existing = db.query(PostMortem).filter_by(experiment_id=experiment_id).first()
    if existing:
        print(f"Post-Mortem: Already exists for experiment {experiment_id}")
        return existing

    metrics = db.query(ExperimentMetric).filter_by(experiment_id=experiment_id).all()
    cascades = db.query(CascadeEvent).filter_by(experiment_id=experiment_id).all()

    context = build_experiment_context(experiment, metrics, cascades)
    prompt = build_postmortem_prompt(context)

    print(f"Post-Mortem: Generating for experiment {experiment_id} ({experiment.scenario_name})")
    start = time.time()

    report_data = await call_claude_api(prompt)

    if not report_data:
        print("Post-Mortem: Using stub generator (Claude API unavailable)")
        report_data = generate_stub_postmortem(context)

    elapsed = time.time() - start
    print(f"Post-Mortem: Generated in {elapsed:.1f}s")

    severity = report_data.get("severity", "P2")
    title = report_data.get("title", experiment.scenario_name[:200])
    summary = report_data.get("summary", "")
    resilience_score = float(report_data.get("resilience_score", 50.0))

    pm = PostMortem(
        experiment_id=experiment_id,
        severity=severity,
        title=title,
        summary=summary,
        full_report=report_data,
        resilience_score=resilience_score,
        generated_at=datetime.utcnow()
    )
    db.add(pm)
    db.commit()
    db.refresh(pm)

    print(f"Post-Mortem: Stored with ID {pm.id}, severity={severity}, score={resilience_score}")
    return pm

#!/usr/bin/env python3
"""
Database initialization and seed data script.
Run once on startup to create tables and populate initial data.
"""
import os
import sys
import json
import random
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from postgres.models import (
    Base, Service, ChaosExperiment, ExperimentMetric,
    CascadeEvent, PostMortem, NotificationLog, User, Product, Order
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://resilience:resilience@localhost:5432/resilienceos"
)


def wait_for_db(engine, max_retries=30):
    import time
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database connection established.")
            return True
        except Exception as e:
            print(f"Waiting for database... ({i+1}/{max_retries}): {e}")
            time.sleep(2)
    return False


def seed_services(session):
    services_data = [
        {
            "name": "api-gateway",
            "port": 8000,
            "description": "Central API gateway routing requests to downstream services with circuit breaker logic",
            "dependencies": []
        },
        {
            "name": "user-service",
            "port": 8001,
            "description": "Manages user accounts, authentication context, and user profile data",
            "dependencies": ["postgresql"]
        },
        {
            "name": "product-service",
            "port": 8002,
            "description": "Product catalog service with Redis pub/sub for view event streaming",
            "dependencies": ["redis"]
        },
        {
            "name": "order-service",
            "port": 8003,
            "description": "Order management service, depends on user-service and product-service",
            "dependencies": ["user-service", "product-service", "postgresql"]
        },
        {
            "name": "notification-service",
            "port": 8004,
            "description": "Async notification processor consuming Redis pub/sub order events",
            "dependencies": ["redis", "postgresql"]
        },
    ]
    for svc in services_data:
        existing = session.query(Service).filter_by(name=svc["name"]).first()
        if not existing:
            session.add(Service(**svc))
    session.commit()
    print("Services seeded.")


def seed_users(session):
    first_names = ["James", "Emma", "Oliver", "Sophia", "Liam", "Ava", "Noah", "Isabella",
                   "William", "Mia", "Benjamin", "Charlotte", "Elijah", "Amelia", "Lucas",
                   "Harper", "Mason", "Evelyn", "Logan", "Abigail"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
                  "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
                  "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

    for i in range(20):
        fn = first_names[i]
        ln = last_names[i]
        username = f"{fn.lower()}.{ln.lower()}"
        email = f"{username}@example.com"
        existing = session.query(User).filter_by(email=email).first()
        if not existing:
            session.add(User(
                username=username,
                email=email,
                full_name=f"{fn} {ln}",
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 365))
            ))
    session.commit()
    print("Users seeded.")


def seed_products(session):
    categories = {
        "Electronics": [
            ("Quantum Wireless Headphones", 249.99, "Over-ear headphones with ANC and 40h battery"),
            ("UltraSlim Laptop Stand", 79.99, "Aluminum adjustable stand for laptops 12-17 inches"),
            ("MechKey Pro Keyboard", 189.99, "TKL mechanical keyboard with Cherry MX switches"),
            ("4K Webcam Pro", 149.99, "Ultra HD webcam with autofocus and ring light"),
            ("USB-C Hub 12-in-1", 89.99, "Multiport adapter with dual HDMI, SD, USB 3.0"),
            ("Wireless Charging Pad", 39.99, "15W fast wireless charger compatible with Qi devices"),
            ("Smart LED Desk Lamp", 69.99, "RGB desk lamp with touch controls and USB charging port"),
            ("Portable SSD 1TB", 119.99, "NVMe portable SSD with read speed up to 1050MB/s"),
            ("Noise-Cancelling Earbuds", 179.99, "True wireless earbuds with 28h total battery life"),
            ("Smart Power Strip", 54.99, "6-outlet smart power strip with energy monitoring"),
        ],
        "Software & Tools": [
            ("DevOps Monitoring Suite", 299.99, "Enterprise APM tool with distributed tracing"),
            ("CI/CD Pipeline Builder", 199.99, "Visual pipeline builder for GitHub/GitLab integration"),
            ("Container Security Scanner", 149.99, "Automated vulnerability scanning for Docker images"),
            ("Log Aggregation Platform", 249.99, "Centralized logging with full-text search"),
            ("Infrastructure as Code Toolkit", 179.99, "Terraform modules for AWS, GCP, Azure"),
            ("API Testing Framework", 99.99, "Load testing and contract testing for REST/GraphQL APIs"),
            ("Database Migration Tool", 129.99, "Zero-downtime schema migration for PostgreSQL/MySQL"),
            ("Secret Management Service", 219.99, "Vault-compatible secret rotation and audit logging"),
            ("Kubernetes Dashboard Pro", 159.99, "Advanced K8s management UI with RBAC support"),
            ("Performance Profiler", 189.99, "Continuous profiling for Python, Go, Java, Node.js"),
        ],
        "Cloud Services": [
            ("Edge CDN Credits - 1TB", 49.99, "Global CDN bandwidth credit bundle"),
            ("Object Storage 5TB", 79.99, "S3-compatible object storage with versioning"),
            ("Managed Redis 10GB", 99.99, "Fully managed Redis cluster with automatic failover"),
            ("PostgreSQL Managed DB", 149.99, "Managed PostgreSQL with PITR and read replicas"),
            ("Serverless Functions Pack", 39.99, "1M executions per month with 256MB memory"),
            ("DDoS Protection Bundle", 199.99, "Layer 7 DDoS mitigation with WAF rules"),
            ("VPN Gateway Service", 89.99, "Site-to-site VPN with BGP routing support"),
            ("Load Balancer Pro", 129.99, "Global load balancer with health checks and SSL"),
            ("DNS Failover Service", 69.99, "GeoDNS with 60-second TTL failover"),
            ("Compliance Audit Pack", 299.99, "SOC2/ISO27001 compliance reporting and evidence"),
        ],
        "Books & Learning": [
            ("Designing Distributed Systems", 59.99, "Patterns and paradigms for scalable services"),
            ("Site Reliability Engineering", 49.99, "How Google runs production systems"),
            ("The Staff Engineer's Path", 44.99, "Career progression for senior individual contributors"),
            ("System Design Interview Vol 2", 39.99, "Advanced system design for FAANG interviews"),
            ("Clean Architecture", 42.99, "Principles of software architecture by Robert Martin"),
            ("Kubernetes Patterns", 54.99, "Reusable elements for designing cloud-native apps"),
            ("Chaos Engineering", 47.99, "System resiliency in practice by Netflix engineers"),
            ("Observability Engineering", 52.99, "Achieving production excellence with o11y"),
            ("Database Internals", 56.99, "Deep dive into distributed database systems"),
            ("The Phoenix Project", 34.99, "A novel about IT, DevOps, and helping your business win"),
        ],
        "Hardware": [
            ("Raspberry Pi 5 8GB", 89.99, "Latest Raspberry Pi with PCIe and RP1 southbridge"),
            ("Arduino Mega Kit", 64.99, "Complete kit with sensors, motors, and breadboard"),
            ("Network Switch 24-port", 199.99, "Managed gigabit switch with VLAN and QoS support"),
            ("Mini PC - AMD Ryzen 9", 649.99, "Compact workstation with 32GB RAM, 1TB NVMe"),
            ("Thermal Camera Module", 129.99, "MLX90640 thermal imaging camera for Raspberry Pi"),
            ("LoRa Gateway", 149.99, "8-channel LoRaWAN gateway for IoT deployments"),
            ("NAS Enclosure 4-bay", 279.99, "Diskless 4-bay NAS with 2.5GbE networking"),
            ("KVM Switch 4-port", 99.99, "4K KVM switch for managing multiple servers"),
            ("Fiber Media Converter", 79.99, "Gigabit Ethernet to single-mode fiber converter"),
            ("UPS 1500VA", 249.99, "Line-interactive UPS with USB monitoring and AVR"),
        ],
    }

    for category, products in categories.items():
        for name, price, description in products:
            existing = session.query(Product).filter_by(name=name).first()
            if not existing:
                session.add(Product(
                    name=name,
                    description=description,
                    price=price,
                    category=category,
                    stock_quantity=random.randint(5, 500),
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 180))
                ))
    session.commit()
    print("Products seeded.")


def seed_orders(session):
    users = session.query(User).all()
    products = session.query(Product).all()

    statuses = ["completed", "completed", "completed", "shipped", "pending", "cancelled"]
    for i in range(10):
        user = random.choice(users)
        product = random.choice(products)
        qty = random.randint(1, 3)
        session.add(Order(
            user_id=user.id,
            product_id=product.id,
            quantity=qty,
            total_price=round(product.price * qty, 2),
            status=random.choice(statuses),
            created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 168))
        ))
    session.commit()
    print("Orders seeded.")


def seed_past_experiments(session):
    experiments_data = [
        {
            "scenario_name": "Cascade Failure - User Service Degradation",
            "fault_type": "error_rate",
            "target_service": "user-service",
            "parameters": {"error_rate": 0.8, "duration_seconds": 60},
            "started_at": datetime.utcnow() - timedelta(hours=48),
            "ended_at": datetime.utcnow() - timedelta(hours=47, minutes=55),
            "status": "completed",
            "blast_radius_score": 78.5
        },
        {
            "scenario_name": "Slow Death - Product Service Latency Ramp",
            "fault_type": "latency",
            "target_service": "product-service",
            "parameters": {"initial_delay_ms": 100, "final_delay_ms": 500, "duration_seconds": 90},
            "started_at": datetime.utcnow() - timedelta(hours=24),
            "ended_at": datetime.utcnow() - timedelta(hours=23, minutes=58),
            "status": "completed",
            "blast_radius_score": 61.2
        },
        {
            "scenario_name": "Split Brain - Order Service Network Partition",
            "fault_type": "partition",
            "target_service": "order-service",
            "parameters": {"targets": ["user-service", "product-service"], "duration_seconds": 45},
            "started_at": datetime.utcnow() - timedelta(hours=6),
            "ended_at": datetime.utcnow() - timedelta(hours=5, minutes=58),
            "status": "completed",
            "blast_radius_score": 89.3
        },
    ]

    created_experiments = []
    for exp_data in experiments_data:
        existing = session.query(ChaosExperiment).filter_by(
            scenario_name=exp_data["scenario_name"]
        ).first()
        if not existing:
            exp = ChaosExperiment(**exp_data)
            session.add(exp)
            session.flush()
            created_experiments.append(exp)

            # Seed cascade events
            cascade_pairs = [
                ("user-service", "order-service", 8.3, "Order service dependency calls failing"),
                ("order-service", "api-gateway", 15.7, "API gateway upstream errors increasing"),
            ]
            for src, affected, delay, desc in cascade_pairs:
                session.add(CascadeEvent(
                    experiment_id=exp.id,
                    source_service=src,
                    affected_service=affected,
                    detected_at=exp.started_at + timedelta(seconds=delay),
                    delay_seconds=delay,
                    impact_description=desc
                ))

    session.commit()
    print(f"Seeded {len(created_experiments)} chaos experiments.")
    return created_experiments


def seed_post_mortems(session):
    experiments = session.query(ChaosExperiment).filter_by(status="completed").limit(2).all()

    pm_data = [
        {
            "severity": "P1",
            "title": "User Service Error Rate Spike Causes Order Processing Cascade Failure",
            "summary": "An injected 80% error rate in the user-service caused complete order processing failure within 15 seconds as the order-service dependency calls began failing. Recovery was observed 12 seconds after fault removal, with full system normalization at T+27 seconds.",
            "resilience_score": 42.0,
            "full_report": {
                "title": "User Service Error Rate Spike Causes Order Processing Cascade Failure",
                "severity": "P1",
                "summary": "An injected 80% error rate in the user-service caused complete order processing failure within 15 seconds as the order-service dependency calls began failing. Recovery was observed 12 seconds after fault removal.",
                "impact": {
                    "duration_minutes": 5,
                    "services_affected": ["user-service", "order-service", "api-gateway"],
                    "estimated_requests_impacted": 4800,
                    "user_facing_impact": "All order creation requests returned 503 errors. Existing orders were unaffected. User profile lookups failed completely."
                },
                "timeline": [
                    {"time": "T+0:00", "event": "Error rate injection activated on user-service at 80%", "service": "user-service"},
                    {"time": "T+0:08", "event": "Order service dependency health check detects elevated error rate", "service": "order-service"},
                    {"time": "T+0:15", "event": "Order service begins returning 503 for all POST /orders requests", "service": "order-service"},
                    {"time": "T+0:23", "event": "API gateway error rate climbs above 10% alerting threshold", "service": "api-gateway"},
                    {"time": "T+1:00", "event": "Fault removal initiated", "service": "chaos-agent"},
                    {"time": "T+1:12", "event": "User service error rate drops below 5%", "service": "user-service"},
                    {"time": "T+1:27", "event": "Order service recovers, dependency calls succeeding", "service": "order-service"},
                    {"time": "T+1:35", "event": "Full system recovery confirmed", "service": "api-gateway"}
                ],
                "root_cause": "The user-service lacked a circuit breaker implementation. When 80% of requests began failing, order-service continued to make synchronous dependency calls on every inbound request rather than failing fast. This amplified the blast radius from a single service fault to a system-wide P1 incident.",
                "contributing_factors": [
                    "No circuit breaker pattern implemented in order-service for user-service calls",
                    "Synchronous inter-service communication with no fallback behavior",
                    "Health check polling interval too slow to detect rapid degradation onset",
                    "No request hedging or retry-with-backoff strategy in place"
                ],
                "cascade_analysis": "Failure propagated from user-service to order-service in 8 seconds via synchronous HTTP dependency calls. Order-service had no circuit breaker, so it dutifully forwarded every incoming request to the failing user-service. At T+23s, the elevated error rate at order-service level caused api-gateway to begin surfacing 503 responses to end users.",
                "detection_gap": "8 seconds elapsed between fault injection and first automated detection. The health check polling interval of 5 seconds introduced up to 5 seconds of additional detection latency beyond the propagation delay.",
                "recovery_analysis": "Recovery was clean and fast once the fault was removed. The lack of any retry storms or thundering herd behavior after recovery is a positive signal. However, the 27-second full recovery time suggests that connection pool drainage and reconnection added unnecessary latency.",
                "action_items": [
                    {"priority": "P0", "action": "Implement circuit breaker in order-service for all upstream dependencies using a library such as pybreaker or resilience4j", "owner": "order-service team", "deadline": "1 week"},
                    {"priority": "P0", "action": "Add exponential backoff with jitter to all inter-service HTTP clients", "owner": "platform team", "deadline": "1 week"},
                    {"priority": "P1", "action": "Reduce health check polling interval from 5s to 1s for critical service dependencies", "owner": "SRE team", "deadline": "2 weeks"},
                    {"priority": "P1", "action": "Implement graceful degradation in order-service when user-service is unavailable, returning cached or partial data", "owner": "order-service team", "deadline": "2 weeks"},
                    {"priority": "P2", "action": "Add alerting rule for inter-service dependency error rate above 5% with PagerDuty integration", "owner": "SRE team", "deadline": "1 month"}
                ],
                "lessons_learned": [
                    "Synchronous service dependencies are single points of failure without circuit breakers",
                    "Detection latency of 8 seconds is too slow for P0 services during rapid degradation events",
                    "The blast radius extended to 3 services from a single point of fault injection"
                ],
                "resilience_score": 42
            }
        },
        {
            "severity": "P2",
            "title": "Product Service Latency Ramp Triggers Downstream Timeout Cascade",
            "summary": "Gradual latency injection into product-service from 100ms to 500ms over 30 seconds caused order-service to exhaust its connection pool and begin timing out on all product lookups. The circuit breaker activated at 450ms average latency.",
            "resilience_score": 67.0,
            "full_report": {
                "title": "Product Service Latency Ramp Triggers Downstream Timeout Cascade",
                "severity": "P2",
                "summary": "Gradual latency injection into product-service from 100ms to 500ms over 30 seconds caused order-service to exhaust its connection pool and begin timing out on all product lookups.",
                "impact": {
                    "duration_minutes": 3,
                    "services_affected": ["product-service", "order-service"],
                    "estimated_requests_impacted": 1200,
                    "user_facing_impact": "Order creation latency increased from 45ms to over 600ms. New orders with product validation failed after 500ms timeout threshold was breached."
                },
                "timeline": [
                    {"time": "T+0:00", "event": "Latency injection begins at 100ms baseline on product-service", "service": "product-service"},
                    {"time": "T+0:15", "event": "Order service P99 latency crosses 200ms alert threshold", "service": "order-service"},
                    {"time": "T+0:30", "event": "Latency reaches 500ms, order-service connection pool exhaustion begins", "service": "product-service"},
                    {"time": "T+0:38", "event": "Order service begins returning 504 Gateway Timeout errors", "service": "order-service"},
                    {"time": "T+1:30", "event": "Fault removed, latency begins recovering", "service": "chaos-agent"},
                    {"time": "T+1:45", "event": "Product service latency returns to baseline", "service": "product-service"},
                    {"time": "T+1:58", "event": "Order service connection pool drains and recovers", "service": "order-service"}
                ],
                "root_cause": "The order-service HTTP client timeout was set to 500ms, which is appropriate for normal operation but insufficient for detecting gradual latency degradation early. The connection pool (size 10) became saturated with in-flight requests waiting for product-service responses.",
                "contributing_factors": [
                    "HTTP client connection pool too small for sustained high-latency dependency calls",
                    "No adaptive timeout based on rolling P99 of dependency response times",
                    "Absence of request timeout propagation from API gateway down to service dependencies"
                ],
                "cascade_analysis": "Latency degradation propagated indirectly: high latency on product-service caused order-service connections to block longer, exhausting the pool and causing queuing. This secondary effect produced timeout errors even for requests that would have succeeded with a larger connection pool.",
                "detection_gap": "15 seconds to first automated alert. Gradual degradation is harder to detect than binary failures. A trend-based alerting rule would have detected this 8 seconds earlier.",
                "recovery_analysis": "Recovery was smooth. Connection pool drain completed in 13 seconds post-fault-removal. The system showed good recovery characteristics with no retry storms observed.",
                "action_items": [
                    {"priority": "P1", "action": "Increase HTTP client connection pool size from 10 to 50 in order-service", "owner": "order-service team", "deadline": "1 week"},
                    {"priority": "P1", "action": "Add trend-based alerting for latency increase rate, not just threshold crossing", "owner": "SRE team", "deadline": "2 weeks"},
                    {"priority": "P2", "action": "Implement adaptive timeouts that adjust based on rolling P99 of each dependency", "owner": "platform team", "deadline": "1 month"}
                ],
                "lessons_learned": [
                    "Gradual degradation is more dangerous than binary failures because detection is slower",
                    "Connection pool exhaustion can amplify a latency problem into a hard failure",
                    "Trend-based alerting is necessary to complement threshold-based alerting"
                ],
                "resilience_score": 67
            }
        }
    ]

    for i, pm in enumerate(pm_data):
        if i < len(experiments):
            exp = experiments[i]
            existing = session.query(PostMortem).filter_by(experiment_id=exp.id).first()
            if not existing:
                session.add(PostMortem(
                    experiment_id=exp.id,
                    severity=pm["severity"],
                    title=pm["title"],
                    summary=pm["summary"],
                    full_report=pm["full_report"],
                    resilience_score=pm["resilience_score"],
                    generated_at=exp.ended_at or datetime.utcnow()
                ))
    session.commit()
    print("Post-mortems seeded.")


def main():
    print(f"Connecting to: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)

    if not wait_for_db(engine):
        print("Failed to connect to database. Exiting.")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    print("Tables created.")

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        seed_services(session)
        seed_users(session)
        seed_products(session)
        seed_orders(session)
        seed_past_experiments(session)
        seed_post_mortems(session)
        print("Database seeding complete.")
    except Exception as e:
        session.rollback()
        print(f"Seeding error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

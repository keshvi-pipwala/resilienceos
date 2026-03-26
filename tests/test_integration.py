"""
ResilienceOS Integration Tests
Tests the full stack: microservices, chaos injection, cascade detection, post-mortems.

Usage (with stack running via docker compose up):
    pip install pytest httpx pytest-asyncio
    pytest tests/test_integration.py -v

Usage (quick smoke test only):
    pytest tests/test_integration.py -v -m smoke
"""
import asyncio
import time
import pytest
import httpx

BASE = {
    "gateway":      "http://localhost:8000",
    "user":         "http://localhost:8001",
    "product":      "http://localhost:8002",
    "order":        "http://localhost:8003",
    "notification": "http://localhost:8004",
    "chaos":        "http://localhost:8010",
    "control":      "http://localhost:9000",
}

TIMEOUT = httpx.Timeout(10.0)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def client():
    with httpx.Client(timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(autouse=True)
def stop_all_chaos(client):
    """Ensure chaos is cleared before and after every test."""
    client.post(f"{BASE['chaos']}/chaos/stop-all")
    yield
    client.post(f"{BASE['chaos']}/chaos/stop-all")


# ── Smoke tests: all services are reachable and healthy ───────────────────


@pytest.mark.smoke
class TestServiceHealth:

    def test_api_gateway_health(self, client):
        r = client.get(f"{BASE['gateway']}/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_user_service_health(self, client):
        r = client.get(f"{BASE['user']}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "error_rate" in data
        assert "avg_latency_ms" in data

    def test_product_service_health(self, client):
        r = client.get(f"{BASE['product']}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_order_service_health(self, client):
        r = client.get(f"{BASE['order']}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "dependency_health" in data
        assert "user-service" in data["dependency_health"]
        assert "product-service" in data["dependency_health"]

    def test_notification_service_health(self, client):
        r = client.get(f"{BASE['notification']}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_chaos_agent_health(self, client):
        r = client.get(f"{BASE['chaos']}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_control_plane_health(self, client):
        r = client.get(f"{BASE['control']}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


# ── Prometheus metrics endpoints ──────────────────────────────────────────


@pytest.mark.smoke
class TestMetricsEndpoints:

    def test_gateway_metrics(self, client):
        r = client.get(f"{BASE['gateway']}/metrics")
        assert r.status_code == 200
        assert "api_gateway_requests_total" in r.text
        assert "api_gateway_error_rate" in r.text
        assert "api_gateway_uptime_seconds" in r.text

    def test_user_service_metrics(self, client):
        r = client.get(f"{BASE['user']}/metrics")
        assert r.status_code == 200
        assert "user_service_requests_total" in r.text

    def test_order_service_metrics_includes_deps(self, client):
        r = client.get(f"{BASE['order']}/metrics")
        assert r.status_code == 200
        assert "order_service_user_dep_success_rate" in r.text
        assert "order_service_product_dep_success_rate" in r.text


# ── Seed data: products and users exist ───────────────────────────────────


@pytest.mark.smoke
class TestSeedData:

    def test_products_seeded(self, client):
        r = client.get(f"{BASE['product']}/products")
        assert r.status_code == 200
        products = r.json()
        assert len(products) >= 50, f"Expected 50+ products, got {len(products)}"

    def test_users_seeded(self, client):
        r = client.get(f"{BASE['user']}/users")
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 20, f"Expected 20+ users, got {len(users)}"

    def test_product_categories(self, client):
        r = client.get(f"{BASE['product']}/products?limit=100")
        assert r.status_code == 200
        products = r.json()
        categories = {p["category"] for p in products}
        expected = {"Electronics", "Software & Tools", "Cloud Services", "Books & Learning", "Hardware"}
        assert expected.issubset(categories), f"Missing categories: {expected - categories}"

    def test_product_has_required_fields(self, client):
        r = client.get(f"{BASE['product']}/products/1")
        assert r.status_code == 200
        p = r.json()
        for field in ("id", "name", "price", "category", "stock_quantity"):
            assert field in p, f"Missing field: {field}"
        assert p["price"] > 0
        assert p["stock_quantity"] >= 0


# ── Order creation: real inter-service call ───────────────────────────────


class TestOrderCreation:

    def test_create_order_calls_user_and_product(self, client):
        """Order creation requires both user-service and product-service to respond."""
        # Get real IDs from seed data
        users = client.get(f"{BASE['user']}/users?limit=1").json()
        products = client.get(f"{BASE['product']}/products?limit=1").json()
        assert users and products

        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": users[0]["id"],
            "product_id": products[0]["id"],
            "quantity": 1
        })
        assert r.status_code == 201
        order = r.json()
        assert order["user_id"] == users[0]["id"]
        assert order["product_id"] == products[0]["id"]
        assert order["total_price"] > 0
        assert order["status"] == "pending"

    def test_order_fails_with_invalid_user(self, client):
        products = client.get(f"{BASE['product']}/products?limit=1").json()
        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": 999999,
            "product_id": products[0]["id"],
            "quantity": 1
        })
        assert r.status_code == 404

    def test_list_orders(self, client):
        r = client.get(f"{BASE['order']}/orders")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 10  # Seeded orders


# ── Chaos injection: latency fault ────────────────────────────────────────


class TestLatencyInjection:

    def test_inject_and_clear_latency(self, client):
        """Inject 300ms latency, verify service slows down, clear and verify recovery."""
        # Baseline latency
        t0 = time.time()
        r = client.get(f"{BASE['product']}/products/1")
        baseline_ms = (time.time() - t0) * 1000
        assert r.status_code == 200

        # Inject chaos
        r = client.post(f"{BASE['product']}/chaos/configure", json={
            "enabled": True,
            "latency_ms": 300,
            "error_rate": 0.0,
            "jitter_ms": 0
        })
        assert r.status_code == 200
        assert r.json()["status"] == "applied"

        # Request should now be slower
        t0 = time.time()
        r = client.get(f"{BASE['product']}/products/1")
        chaos_ms = (time.time() - t0) * 1000
        assert r.status_code == 200
        assert chaos_ms >= 280, f"Expected >= 280ms with chaos, got {chaos_ms:.0f}ms"

        # Clear chaos
        r = client.post(f"{BASE['product']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })
        assert r.status_code == 200

        # Should be fast again
        t0 = time.time()
        r = client.get(f"{BASE['product']}/products/1")
        recovery_ms = (time.time() - t0) * 1000
        assert recovery_ms < 200, f"Expected recovery, got {recovery_ms:.0f}ms"

    def test_health_shows_chaos_active(self, client):
        """Health endpoint reports chaos_enabled=True when chaos is active."""
        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": True, "latency_ms": 100, "error_rate": 0.0, "jitter_ms": 0
        })
        r = client.get(f"{BASE['user']}/health")
        assert r.status_code == 200
        assert r.json().get("chaos_enabled") is True

        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })
        r = client.get(f"{BASE['user']}/health")
        assert r.json().get("chaos_enabled") is False


# ── Chaos injection: error rate fault ─────────────────────────────────────


class TestErrorRateInjection:

    def test_inject_100pct_errors(self, client):
        """100% error rate should cause all requests to fail with 500."""
        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": True, "latency_ms": 0, "error_rate": 1.0, "jitter_ms": 0
        })
        for _ in range(5):
            r = client.get(f"{BASE['user']}/users")
            assert r.status_code == 500, f"Expected 500 with 100% error rate, got {r.status_code}"

        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })

    def test_error_rate_reflected_in_health(self, client):
        """After injecting errors, health endpoint should show elevated error_rate."""
        # Generate some requests to populate error_rate metric
        client.post(f"{BASE['product']}/chaos/configure", json={
            "enabled": True, "latency_ms": 0, "error_rate": 0.8, "jitter_ms": 0
        })
        # Hit the service multiple times to rack up errors
        for _ in range(10):
            client.get(f"{BASE['product']}/products")

        r = client.get(f"{BASE['product']}/health")
        health = r.json()
        assert health["error_rate"] > 0.3, f"Expected elevated error_rate, got {health['error_rate']}"

        client.post(f"{BASE['product']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })


# ── The Real Cascade: user-service errors propagate to order-service ──────


class TestRealCascadeFailure:

    def test_user_service_errors_cascade_to_order_service(self, client):
        """
        The core distributed systems demonstration:
        When user-service has 100% errors, POST /orders must fail.
        This is real cascade failure — not simulated.
        """
        users = client.get(f"{BASE['user']}/users?limit=1").json()
        products = client.get(f"{BASE['product']}/products?limit=1").json()
        user_id = users[0]["id"]
        product_id = products[0]["id"]

        # Verify order works before chaos
        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": user_id, "product_id": product_id, "quantity": 1
        })
        assert r.status_code == 201, f"Pre-chaos order should succeed, got {r.status_code}"

        # Inject 100% errors into user-service
        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": True, "latency_ms": 0, "error_rate": 1.0, "jitter_ms": 0
        })

        # Order creation must now fail — it calls user-service synchronously
        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": user_id, "product_id": product_id, "quantity": 1
        })
        assert r.status_code in (503, 504), (
            f"Order should fail when user-service is down, got {r.status_code}: {r.text}"
        )
        assert "user" in r.json().get("detail", "").lower() or "service" in r.json().get("detail", "").lower()

        # Restore user-service
        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })

        # Verify order works again after recovery
        time.sleep(0.5)
        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": user_id, "product_id": product_id, "quantity": 1
        })
        assert r.status_code == 201, f"Post-recovery order should succeed, got {r.status_code}: {r.text}"

    def test_product_service_errors_cascade_to_order_service(self, client):
        """Product-service failure also cascades to order-service."""
        users = client.get(f"{BASE['user']}/users?limit=1").json()
        products = client.get(f"{BASE['product']}/products?limit=1").json()

        client.post(f"{BASE['product']}/chaos/configure", json={
            "enabled": True, "latency_ms": 0, "error_rate": 1.0, "jitter_ms": 0
        })

        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": users[0]["id"],
            "product_id": products[0]["id"],
            "quantity": 1
        })
        assert r.status_code in (503, 504), (
            f"Order should fail when product-service is down, got {r.status_code}"
        )

        client.post(f"{BASE['product']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })

    def test_dependency_health_degrades_under_chaos(self, client):
        """order-service /health dependency_health should show degraded rates."""
        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": True, "latency_ms": 0, "error_rate": 1.0, "jitter_ms": 0
        })

        users = client.get(f"{BASE['user']}/users?limit=1").json()
        products = client.get(f"{BASE['product']}/products?limit=1").json()

        # Fire several order requests to populate dep metrics
        for _ in range(5):
            client.post(f"{BASE['order']}/orders", json={
                "user_id": users[0]["id"] if users else 1,
                "product_id": products[0]["id"] if products else 1,
                "quantity": 1
            })

        r = client.get(f"{BASE['order']}/health")
        health = r.json()
        user_dep_rate = health["dependency_health"]["user-service"]
        assert user_dep_rate < 0.5, (
            f"user-service dep success rate should be low under chaos, got {user_dep_rate}"
        )

        client.post(f"{BASE['user']}/chaos/configure", json={
            "enabled": False, "latency_ms": 0, "error_rate": 0.0, "jitter_ms": 0
        })


# ── Chaos Agent API ────────────────────────────────────────────────────────


class TestChaosAgentAPI:

    def test_inject_latency_via_agent(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/latency", json={
            "target": "product-service",
            "delay_ms": 200,
            "jitter_ms": 0,
            "duration_seconds": 10
        })
        assert r.status_code == 200
        data = r.json()
        assert "experiment_id" in data
        assert data["status"] == "started"
        assert data["fault_type"] == "latency"
        assert isinstance(data["experiment_id"], int)

    def test_inject_error_rate_via_agent(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/errors", json={
            "target": "notification-service",
            "error_rate": 0.3,
            "duration_seconds": 10
        })
        assert r.status_code == 200
        assert r.json()["fault_type"] == "error_rate"

    def test_active_chaos_shows_running_experiments(self, client):
        client.post(f"{BASE['chaos']}/chaos/latency", json={
            "target": "product-service",
            "delay_ms": 100,
            "jitter_ms": 0,
            "duration_seconds": 30
        })
        time.sleep(1)
        r = client.get(f"{BASE['chaos']}/chaos/active")
        assert r.status_code == 200
        data = r.json()
        assert "active_experiments" in data
        assert "active_faults" in data
        assert len(data["active_experiments"]) >= 1

    def test_stop_all_clears_experiments(self, client):
        client.post(f"{BASE['chaos']}/chaos/latency", json={
            "target": "user-service",
            "delay_ms": 500,
            "jitter_ms": 0,
            "duration_seconds": 60
        })
        time.sleep(1)

        r = client.post(f"{BASE['chaos']}/chaos/stop-all")
        assert r.status_code == 200
        assert r.json()["status"] == "all_stopped"

        time.sleep(1)
        r = client.get(f"{BASE['chaos']}/chaos/active")
        assert len(r.json()["active_experiments"]) == 0

        # Service should be fast again after stop
        t0 = time.time()
        client.get(f"{BASE['user']}/users")
        elapsed_ms = (time.time() - t0) * 1000
        assert elapsed_ms < 300, f"Expected fast response after stop-all, got {elapsed_ms:.0f}ms"

    def test_experiment_recorded_in_db(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/errors", json={
            "target": "api-gateway",
            "error_rate": 0.1,
            "duration_seconds": 5
        })
        exp_id = r.json()["experiment_id"]

        # Check it appears in experiment list
        r = client.get(f"{BASE['chaos']}/chaos/experiments")
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert exp_id in ids

    def test_kill_fault_via_agent(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/kill", json={
            "target": "notification-service",
            "restart_after_seconds": 5
        })
        assert r.status_code == 200
        data = r.json()
        assert data["fault_type"] == "kill"
        assert data["target"] == "notification-service"


# ── Control Plane API ──────────────────────────────────────────────────────


class TestControlPlaneAPI:

    def test_all_services_health_aggregated(self, client):
        r = client.get(f"{BASE['control']}/api/services/health")
        assert r.status_code == 200
        health = r.json()
        expected_services = {
            "api-gateway", "user-service", "product-service",
            "order-service", "notification-service"
        }
        assert expected_services.issubset(set(health.keys()))
        for svc, h in health.items():
            assert "status" in h

    def test_services_registry(self, client):
        r = client.get(f"{BASE['control']}/api/services")
        assert r.status_code == 200
        services = r.json()
        assert len(services) >= 5
        names = {s["name"] for s in services}
        assert "api-gateway" in names
        assert "order-service" in names

    def test_chaos_proxied_correctly(self, client):
        r = client.post(f"{BASE['control']}/api/chaos/errors", json={
            "target": "product-service",
            "error_rate": 0.1,
            "duration_seconds": 5
        })
        assert r.status_code == 200
        assert "experiment_id" in r.json()

    def test_experiment_history_via_control_plane(self, client):
        r = client.get(f"{BASE['control']}/api/chaos/experiments")
        assert r.status_code == 200
        experiments = r.json()
        assert isinstance(experiments, list)
        assert len(experiments) >= 3  # Seeded experiments

    def test_postmortems_list(self, client):
        r = client.get(f"{BASE['control']}/api/postmortems")
        assert r.status_code == 200
        pms = r.json()
        assert isinstance(pms, list)
        assert len(pms) >= 2  # Seeded post-mortems

    def test_postmortem_detail_has_full_report(self, client):
        pms = client.get(f"{BASE['control']}/api/postmortems").json()
        assert pms, "No post-mortems found"
        pm_id = pms[0]["id"]

        r = client.get(f"{BASE['control']}/api/postmortems/{pm_id}")
        assert r.status_code == 200
        pm = r.json()
        assert "full_report" in pm
        report = pm["full_report"]
        for field in ("title", "severity", "summary", "impact", "timeline",
                      "root_cause", "action_items", "resilience_score"):
            assert field in report, f"Post-mortem missing field: {field}"

    def test_postmortem_generation_triggers(self, client):
        """Trigger post-mortem generation for a completed experiment without one."""
        exps = client.get(f"{BASE['control']}/api/chaos/experiments").json()
        without_pm = [e for e in exps if e["status"] == "completed" and not e["has_post_mortem"]]

        if not without_pm:
            pytest.skip("All experiments already have post-mortems")

        exp_id = without_pm[0]["id"]
        r = client.post(f"{BASE['control']}/api/postmortems/generate/{exp_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "generating"

    def test_cascade_events_endpoint(self, client):
        r = client.get(f"{BASE['control']}/api/cascade/events")
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        if events:
            e = events[0]
            for field in ("source_service", "affected_service", "delay_seconds"):
                assert field in e

    def test_active_chaos_via_control_plane(self, client):
        r = client.get(f"{BASE['control']}/api/chaos/active")
        assert r.status_code == 200
        data = r.json()
        assert "active_experiments" in data
        assert "active_faults" in data


# ── Chaos headers: per-request override ───────────────────────────────────


class TestChaosHeaders:

    def test_x_chaos_error_rate_header(self, client):
        """X-Chaos-Enabled + X-Chaos-Error-Rate headers force errors on a single request."""
        headers = {
            "X-Chaos-Enabled": "true",
            "X-Chaos-Error-Rate": "1.0"
        }
        r = client.get(f"{BASE['product']}/products", headers=headers)
        assert r.status_code == 500

    def test_x_chaos_latency_header(self, client):
        """X-Chaos-Latency-Ms header adds artificial delay."""
        headers = {
            "X-Chaos-Enabled": "true",
            "X-Chaos-Latency-Ms": "300"
        }
        t0 = time.time()
        r = client.get(f"{BASE['user']}/users", headers=headers)
        elapsed_ms = (time.time() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms >= 280, f"Expected >= 280ms, got {elapsed_ms:.0f}ms"

    def test_chaos_headers_do_not_affect_health_endpoint(self, client):
        """Health and metrics endpoints are exempt from chaos injection."""
        headers = {
            "X-Chaos-Enabled": "true",
            "X-Chaos-Error-Rate": "1.0",
            "X-Chaos-Latency-Ms": "5000"
        }
        t0 = time.time()
        r = client.get(f"{BASE['product']}/health", headers=headers)
        elapsed_ms = (time.time() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 500, f"Health endpoint should not be affected by chaos headers"


# ── Scenario runner ────────────────────────────────────────────────────────


class TestScenarioRunner:

    def test_cascade_failure_scenario_starts(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/scenario", json={
            "scenario": "cascade_failure"
        })
        assert r.status_code == 200
        data = r.json()
        assert "experiment_id" in data
        assert data["scenario"] == "cascade_failure"
        assert data["status"] == "started"

    def test_invalid_scenario_returns_400(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/scenario", json={
            "scenario": "nonexistent_scenario"
        })
        assert r.status_code == 400

    def test_slow_death_scenario_starts(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/scenario", json={
            "scenario": "slow_death"
        })
        assert r.status_code == 200
        assert r.json()["scenario"] == "slow_death"

    def test_split_brain_scenario_starts(self, client):
        r = client.post(f"{BASE['chaos']}/chaos/scenario", json={
            "scenario": "split_brain"
        })
        assert r.status_code == 200
        assert r.json()["scenario"] == "split_brain"


# ── API Gateway proxy and circuit breaker ─────────────────────────────────


class TestAPIGatewayProxy:

    def test_gateway_proxies_products(self, client):
        r = client.get(f"{BASE['gateway']}/api/products")
        assert r.status_code == 200
        products = r.json()
        assert len(products) >= 50

    def test_gateway_proxies_users(self, client):
        r = client.get(f"{BASE['gateway']}/api/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_gateway_status_shows_circuit_breakers(self, client):
        r = client.get(f"{BASE['gateway']}/status")
        assert r.status_code == 200
        data = r.json()
        assert "circuit_breakers" in data
        cb = data["circuit_breakers"]
        for svc in ("user-service", "product-service", "order-service"):
            assert svc in cb
            assert cb[svc]["state"] in ("closed", "open", "half-open")

    def test_gateway_proxies_order_creation(self, client):
        users = client.get(f"{BASE['gateway']}/api/users?limit=1").json()
        products = client.get(f"{BASE['gateway']}/api/products?limit=1").json()

        r = client.post(f"{BASE['gateway']}/api/orders", json={
            "user_id": users[0]["id"],
            "product_id": products[0]["id"],
            "quantity": 1
        })
        assert r.status_code == 201


# ── Data integrity ────────────────────────────────────────────────────────


class TestDataIntegrity:

    def test_order_price_calculation(self, client):
        """Order total_price must equal product.price * quantity."""
        products = client.get(f"{BASE['product']}/products?limit=1").json()
        users = client.get(f"{BASE['user']}/users?limit=1").json()
        product = products[0]
        qty = 2

        r = client.post(f"{BASE['order']}/orders", json={
            "user_id": users[0]["id"],
            "product_id": product["id"],
            "quantity": qty
        })
        assert r.status_code == 201
        order = r.json()
        expected_price = round(product["price"] * qty, 2)
        assert abs(order["total_price"] - expected_price) < 0.01

    def test_created_user_is_retrievable(self, client):
        import random, string
        suffix = ''.join(random.choices(string.ascii_lowercase, k=6))
        username = f"test_{suffix}"
        email = f"{username}@test.com"

        r = client.post(f"{BASE['user']}/users", json={
            "username": username,
            "email": email,
            "full_name": "Test User"
        })
        assert r.status_code == 201
        user_id = r.json()["id"]

        r = client.get(f"{BASE['user']}/users/{user_id}")
        assert r.status_code == 200
        assert r.json()["email"] == email

    def test_duplicate_user_rejected(self, client):
        """Creating a user with a duplicate email returns 409."""
        users = client.get(f"{BASE['user']}/users?limit=1").json()
        existing = users[0]

        r = client.post(f"{BASE['user']}/users", json={
            "username": "duplicate_test_xyz",
            "email": existing["email"],  # duplicate
            "full_name": "Dupe"
        })
        assert r.status_code == 409

"""
pytest conftest for ResilienceOS integration tests.
Waits for the full stack to be healthy before running any tests.
"""
import time
import pytest
import httpx

SERVICES = {
    "api-gateway":          "http://localhost:8000/health",
    "user-service":         "http://localhost:8001/health",
    "product-service":      "http://localhost:8002/health",
    "order-service":        "http://localhost:8003/health",
    "notification-service": "http://localhost:8004/health",
    "chaos-agent":          "http://localhost:8010/health",
    "control-plane":        "http://localhost:9000/health",
}

MAX_WAIT = 120  # seconds
POLL_INTERVAL = 3


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: quick smoke tests")


def wait_for_stack():
    """Block until all services respond healthy, or raise after MAX_WAIT."""
    print(f"\nWaiting for ResilienceOS stack (up to {MAX_WAIT}s)...")
    deadline = time.time() + MAX_WAIT
    pending = set(SERVICES.keys())

    while pending and time.time() < deadline:
        still_pending = set()
        for name in pending:
            url = SERVICES[name]
            try:
                r = httpx.get(url, timeout=3.0)
                if r.status_code == 200:
                    print(f"  ready: {name}")
                    continue
            except Exception:
                pass
            still_pending.add(name)

        pending = still_pending
        if pending:
            time.sleep(POLL_INTERVAL)

    if pending:
        raise RuntimeError(
            f"Stack not ready after {MAX_WAIT}s. "
            f"Still unreachable: {', '.join(sorted(pending))}.\n"
            f"Run: docker compose up --build"
        )
    print("All services ready.\n")


def pytest_sessionstart(session):
    """Called once before any tests run."""
    # Only wait if we're not in collect-only mode
    if not session.config.option.collectonly:
        wait_for_stack()

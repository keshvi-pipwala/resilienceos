#!/usr/bin/env python3
"""
ResilienceOS Load Generator
Drives continuous realistic traffic through the microservices so that
Prometheus metrics and health checks have meaningful data to display.

Usage:
    python scripts/generate_load.py [--base-url http://localhost:8000] [--rps 5]
"""
import asyncio
import random
import argparse
import time
import sys

import httpx

DEFAULT_BASE = "http://localhost:8000"

# Relative weights of endpoints hit
ENDPOINTS = [
    ("GET", "/api/products",       40),
    ("GET", "/api/users",          20),
    ("GET", "/api/orders",         20),
    ("POST", "/api/orders",        10),
    ("GET", "/api/products/{id}",  10),
]


async def hit_endpoint(client: httpx.AsyncClient, base: str, method: str, path: str, user_ids: list, product_ids: list):
    try:
        if "{id}" in path:
            pid = random.choice(product_ids) if product_ids else random.randint(1, 50)
            path = path.replace("{id}", str(pid))

        url = base + path
        if method == "GET":
            resp = await client.get(url, timeout=5.0)
        elif method == "POST" and "/orders" in path:
            uid = random.choice(user_ids) if user_ids else random.randint(1, 20)
            pid = random.choice(product_ids) if product_ids else random.randint(1, 50)
            resp = await client.post(url, json={
                "user_id": uid,
                "product_id": pid,
                "quantity": random.randint(1, 3)
            }, timeout=5.0)
        else:
            return

        status = resp.status_code
        if status >= 500:
            print(f"  5xx {method} {path} -> {status}", flush=True)
    except Exception as e:
        print(f"  ERR {method} {path}: {type(e).__name__}", flush=True)


async def fetch_ids(base: str) -> tuple:
    """Fetch actual user and product IDs from the services."""
    user_ids, product_ids = [], []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base}/api/users?limit=20")
            if r.status_code == 200:
                user_ids = [u["id"] for u in r.json()]
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base}/api/products?limit=50")
            if r.status_code == 200:
                product_ids = [p["id"] for p in r.json()]
    except Exception:
        pass
    return user_ids, product_ids


def weighted_choice(endpoints):
    total = sum(w for _, _, w in endpoints)
    r = random.uniform(0, total)
    cumulative = 0
    for method, path, weight in endpoints:
        cumulative += weight
        if r <= cumulative:
            return method, path
    return endpoints[-1][0], endpoints[-1][1]


async def run(base: str, rps: int):
    print(f"Load generator started: {base} at {rps} req/s")
    print("Fetching entity IDs...")
    user_ids, product_ids = await fetch_ids(base)
    print(f"  Found {len(user_ids)} users, {len(product_ids)} products")

    interval = 1.0 / rps
    request_count = 0
    error_count = 0

    async with httpx.AsyncClient(timeout=8.0) as client:
        last_id_refresh = time.time()
        while True:
            method, path = weighted_choice(ENDPOINTS)
            await hit_endpoint(client, base, method, path, user_ids, product_ids)
            request_count += 1

            if request_count % (rps * 10) == 0:
                print(f"  Sent {request_count} requests total", flush=True)

            # Refresh IDs every 60 seconds
            if time.time() - last_id_refresh > 60:
                user_ids, product_ids = await fetch_ids(base)
                last_id_refresh = time.time()

            await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ResilienceOS load generator")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="API gateway base URL")
    parser.add_argument("--rps", type=int, default=3, help="Requests per second")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.base_url, args.rps))
    except KeyboardInterrupt:
        print("\nLoad generator stopped.")

"""Locust load-testing script for Lab 09 (`production_app.py`).

Run locally against a test server bound to 127.0.0.1:
    uv run locust -f labs/lab09-cloud-run-deploy/locustfile.py --host http://127.0.0.1:8080
"""

from __future__ import annotations

import os
from typing import Any

try:
    from locust import HttpUser, between, task
except ImportError:  # Allows importing this module even when locust is not installed
    class HttpUser:  # type: ignore[no-redef]
        pass

    def between(min_wait: float, max_wait: float) -> Any:
        return (min_wait, max_wait)

    def task(weight: int = 1) -> Any:
        def decorator(fn: Any) -> Any:
            return fn
        return decorator


class CloudBuildersTrafficUser(HttpUser):
    """Simulates realistic user traffic hitting the Cloud Run service."""

    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        """Load the test API key from the environment (never hardcoded)."""
        self.api_key = os.getenv("SERVICE_API_KEY", "")

    @task(3)
    def check_health(self) -> None:
        """Lightweight readiness probe hit frequently by load balancers."""
        self.client.get("/healthz", name="/healthz")

    @task(5)
    def fetch_workshop_summary(self) -> None:
        """Authenticated query that benefits from the in-memory TTL cache."""
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        self.client.get(
            "/api/v1/workshops/ws-101/summary",
            headers=headers,
            name="/api/v1/workshops/[id]/summary",
        )

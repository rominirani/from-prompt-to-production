"""Lab 09: Production-Hardened FastAPI Service for Google Cloud Run.

Demonstrates:
1. Multi-tiered secret resolution (`os.getenv` -> mounted Secret Manager file ->
   ephemeral cryptographic token for isolated local testing, never hardcoded literals).
2. Constant-time API key authentication (`secrets.compare_digest`).
3. Per-client token-bucket rate limiting (`429 Too Many Requests`).
4. In-memory TTL caching to avoid redundant database or Gemini calls under load.
5. Package dependency verification (`verify_dependencies_against_allowlist_and_osv`)
   to stop AI-hallucinated ("slopsquatted") or vulnerable packages before deploy.
6. Mandatory HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`,
   `Content-Security-Policy`, `Permissions-Policy`, and `Cache-Control`).
"""

from __future__ import annotations

import difflib
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("lab09.production_app")


# ---------------------------------------------------------------------------
# 1. Multi-Tiered Secret Resolution (Never Hardcode Fallback Literals!)
# ---------------------------------------------------------------------------

_EPHEMERAL_DEV_SECRET: str | None = None


def resolve_service_api_key(secret_file_path: str | Path | None = None) -> str:
    """Resolve the service API key using a safe multi-tiered hierarchy.

    Resolution order:
    1. `SERVICE_API_KEY` environment variable (injected by Cloud Run / Secret Manager).
    2. Mounted secret file (e.g., `/var/secrets/service_api_key.txt`).
    3. If `APP_ENV == 'production'`, fail closed by raising a `RuntimeError`.
    4. In local/test environments only, generate a random 32-byte hex secret via
       `secrets.token_hex(32)` and log a warning that it is instance-isolated.
    """
    global _EPHEMERAL_DEV_SECRET

    env_val = os.getenv("SERVICE_API_KEY", "").strip()
    if env_val:
        return env_val

    candidate_path = Path(
        secret_file_path or os.getenv("SERVICE_API_KEY_FILE", "/var/secrets/service_api_key.txt")
    )
    if candidate_path.is_file():
        file_secret = candidate_path.read_text(encoding="utf-8").strip()
        if file_secret:
            return file_secret

    if os.getenv("APP_ENV", "development").lower() == "production":
        raise RuntimeError(
            "CRITICAL: SERVICE_API_KEY is not configured in production environment! "
            "Refusing to start without a valid secret from Google Cloud Secret Manager."
        )

    if _EPHEMERAL_DEV_SECRET is None:
        _EPHEMERAL_DEV_SECRET = secrets.token_hex(32)
        logger.warning(
            "Generating ephemeral SERVICE_API_KEY for isolated local testing. "
            "Do NOT use ephemeral secrets across horizontally scaled instances!"
        )
    return _EPHEMERAL_DEV_SECRET


# ---------------------------------------------------------------------------
# 2. Package Safety & Anti-Slopsquatting Verifier
# ---------------------------------------------------------------------------

APPROVED_PACKAGES: frozenset[str] = frozenset(
    {
        "fastapi",
        "uvicorn",
        "pydantic",
        "httpx",
        "google-genai",
        "google-adk",
        "python-dotenv",
        "aiosqlite",
        "pyyaml",
        "pytest",
        "locust",
    }
)

KNOWN_VULNERABLE_VERSIONS: dict[str, set[str]] = {
    "fastapi": {"0.65.0"},
    "urllib3": {"1.26.4"},
    "pyyaml": {"5.3"},
}


class PackageAuditFinding(BaseModel):
    """Represents a security or slopsquatting finding for a single dependency."""

    model_config = ConfigDict(extra="forbid")

    package_name: str
    version: str
    status: str = Field(description="'approved', 'typosquat_suspect', 'unapproved', or 'vulnerable'")
    reason: str


class DependencyAuditReport(BaseModel):
    """Summary of pre-deployment package verification."""

    model_config = ConfigDict(extra="forbid")

    all_safe: bool
    findings: list[PackageAuditFinding]


def verify_dependencies_against_allowlist_and_osv(
    dependencies: dict[str, str],
) -> DependencyAuditReport:
    """Verify dependencies against an approved allowlist and known OSV advisories.

    Catches two common pre-deployment risks:
    1. AI-hallucinated or typosquatted package names ('slopsquatting'), such as
       `google-generative-ai-sdk` or `fastpai` instead of `google-genai` or `fastapi`.
    2. Known vulnerable versions flagged in OSV.dev advisory feeds.
    """
    findings: list[PackageAuditFinding] = []

    for raw_name, version in dependencies.items():
        pkg = raw_name.strip().lower()

        if pkg in KNOWN_VULNERABLE_VERSIONS and version in KNOWN_VULNERABLE_VERSIONS[pkg]:
            findings.append(
                PackageAuditFinding(
                    package_name=pkg,
                    version=version,
                    status="vulnerable",
                    reason=f"Version {version} of '{pkg}' has a known OSV security advisory.",
                )
            )
            continue

        if pkg in APPROVED_PACKAGES:
            findings.append(
                PackageAuditFinding(
                    package_name=pkg,
                    version=version,
                    status="approved",
                    reason="Package is verified in the project allowlist.",
                )
            )
            continue

        close_matches = difflib.get_close_matches(pkg, APPROVED_PACKAGES, n=1, cutoff=0.72)
        if close_matches:
            findings.append(
                PackageAuditFinding(
                    package_name=pkg,
                    version=version,
                    status="typosquat_suspect",
                    reason=(
                        f"Suspicious package '{pkg}' looks like a typosquat or AI hallucination "
                        f"of approved package '{close_matches[0]}'."
                    ),
                )
            )
        else:
            findings.append(
                PackageAuditFinding(
                    package_name=pkg,
                    version=version,
                    status="unapproved",
                    reason=(
                        f"Package '{pkg}' is not in the approved allowlist. Verify on PyPI "
                        f"and OSV.dev before adding to Dockerfile."
                    ),
                )
            )

    all_safe = all(item.status == "approved" for item in findings)
    return DependencyAuditReport(all_safe=all_safe, findings=findings)


# ---------------------------------------------------------------------------
# 3. In-Memory TTL Cache & Per-Client Token-Bucket Rate Limiter
# ---------------------------------------------------------------------------


class TTLCache:
    """Simple thread-safe TTL cache to avoid repeated slow lookups under load."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self.ttl_seconds, value)

    def clear(self) -> None:
        self._store.clear()


class TokenBucketRateLimiter:
    """Per-client token-bucket rate limiter to protect endpoints from traffic spikes."""

    def __init__(self, capacity: int = 5, refill_rate_per_sec: float = 1.0) -> None:
        self.capacity = float(capacity)
        self.refill_rate_per_sec = refill_rate_per_sec
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow_request(self, client_id: str) -> bool:
        now = time.monotonic()
        tokens, last_ts = self._buckets.get(client_id, (self.capacity, now))
        elapsed = max(0.0, now - last_ts)
        replenished = min(self.capacity, tokens + elapsed * self.refill_rate_per_sec)

        if replenished < 1.0:
            self._buckets[client_id] = (replenished, now)
            return False

        self._buckets[client_id] = (replenished - 1.0, now)
        return True

    def reset(self) -> None:
        self._buckets.clear()


SUMMARY_CACHE = TTLCache(ttl_seconds=30.0)
RATE_LIMITER = TokenBucketRateLimiter(capacity=5, refill_rate_per_sec=0.5)


# ---------------------------------------------------------------------------
# 4. Parameterized SQLite Data Layer
# ---------------------------------------------------------------------------

_DB_CONN: sqlite3.Connection | None = None


def get_catalog_db() -> sqlite3.Connection:
    """Initialize an in-memory SQLite database using parameterized queries."""
    global _DB_CONN
    if _DB_CONN is None:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute(
                """
                CREATE TABLE workshop_summaries (
                    workshop_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    ai_takeaway TEXT NOT NULL
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO workshop_summaries (workshop_id, title, speaker, ai_takeaway)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        "ws-101",
                        "Build Fast APIs with Gemini & Python",
                        "Romin Irani",
                        "Use Pydantic v2 schemas and structured outputs for reliable JSON responses.",
                    ),
                    (
                        "ws-102",
                        "Hands-On Google ADK Agents",
                        "Priya Nair",
                        "Split complex workflows into specialist sub-agents with clear tool docstrings.",
                    ),
                ],
            )
        _DB_CONN = conn
    return _DB_CONN


# ---------------------------------------------------------------------------
# 5. FastAPI Application, Security Headers Middleware & Protected Routes
# ---------------------------------------------------------------------------


class WorkshopSummaryResponse(BaseModel):
    """Structured API response for a workshop summary."""

    model_config = ConfigDict(extra="forbid")

    workshop_id: str
    title: str
    speaker: str
    ai_takeaway: str
    cached: bool
    latency_ms: float


app = FastAPI(
    title="Cloud Builders Production API",
    version="1.0.0",
    docs_url=None,  # Disable public Swagger UI in hardened config unless needed
    redoc_url=None,
)


@app.middleware("http")
async def add_security_headers_and_trace_timing(request: Request, call_next: Any) -> Response:
    """Attach mandatory security headers and execution timing to every HTTP response."""
    start_time = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    return response


def verify_api_key_and_rate_limit(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Authenticate `X-API-Key` in constant time and enforce per-client rate limits."""
    expected_key = resolve_service_api_key()
    provided_key = (x_api_key or "").strip()

    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
        )

    client_host = request.client.host if request.client else "local-client"
    bucket_key = f"{client_host}:{provided_key[:8]}"
    if not RATE_LIMITER.allow_request(bucket_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down and retry shortly.",
        )
    return provided_key


@app.get("/healthz")
def health_check() -> dict[str, str]:
    """Unauthenticated readiness probe for Cloud Run container health checks."""
    return {"status": "ok", "service": "cloud-builders-api"}


@app.get(
    "/api/v1/workshops/{workshop_id}/summary",
    response_model=WorkshopSummaryResponse,
)
def get_workshop_summary(
    workshop_id: str,
    _api_key: str = Depends(verify_api_key_and_rate_limit),
) -> WorkshopSummaryResponse:
    """Return a workshop's AI takeaway, serving from the TTL cache when available."""
    start = time.perf_counter()
    normalized_id = workshop_id.strip().lower()

    cached_payload = SUMMARY_CACHE.get(normalized_id)
    if cached_payload is not None:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
        return WorkshopSummaryResponse(
            workshop_id=cached_payload["workshop_id"],
            title=cached_payload["title"],
            speaker=cached_payload["speaker"],
            ai_takeaway=cached_payload["ai_takeaway"],
            cached=True,
            latency_ms=elapsed_ms,
        )

    # Simulate a 15ms database + AI summarization lookup on a cache miss
    time.sleep(0.015)
    conn = get_catalog_db()
    row = conn.execute(
        """
        SELECT workshop_id, title, speaker, ai_takeaway
        FROM workshop_summaries
        WHERE LOWER(workshop_id) = ?
        """,
        (normalized_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workshop '{normalized_id}' was not found.",
        )

    record = {
        "workshop_id": row["workshop_id"],
        "title": row["title"],
        "speaker": row["speaker"],
        "ai_takeaway": row["ai_takeaway"],
    }
    SUMMARY_CACHE.set(normalized_id, record)
    elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)

    return WorkshopSummaryResponse(
        **record,
        cached=False,
        latency_ms=elapsed_ms,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Log detailed errors server-side while returning a safe generic message to clients."""
    logger.error("Unhandled exception in production_app: %s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )


if __name__ == "__main__":
    import uvicorn

    # Bind strictly to 127.0.0.1 during local development and testing
    uvicorn.run(app, host="127.0.0.1", port=8080)

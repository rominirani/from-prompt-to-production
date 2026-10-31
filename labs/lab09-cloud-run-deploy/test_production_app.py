"""Automated tests for Lab 09: Production-Hardened FastAPI Service on Cloud Run."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from before_and_after_demo import (
    run_optimization_comparison,
    run_scaling_fairness_demo,
    search_user_safe,
    setup_sample_user_db,
)
from production_app import (
    RATE_LIMITER,
    SUMMARY_CACHE,
    app,
    resolve_service_api_key,
    verify_dependencies_against_allowlist_and_osv,
)

client = TestClient(app)


def _reset_state() -> str:
    """Reset rate limiter and TTL cache, returning the active service API key."""
    RATE_LIMITER.reset()
    SUMMARY_CACHE.clear()
    return resolve_service_api_key()


def test_health_check_and_mandatory_security_headers() -> None:
    """Verify `/healthz` succeeds and sets strict HTTP security headers."""
    _reset_state()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Mandatory security headers check
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_authentication_rejects_missing_or_wrong_api_key() -> None:
    """Verify protected endpoints return 401 when X-API-Key is missing or invalid."""
    _reset_state()

    missing_res = client.get("/api/v1/workshops/ws-101/summary")
    assert missing_res.status_code == 401

    wrong_res = client.get(
        "/api/v1/workshops/ws-101/summary",
        headers={"X-API-Key": "wrong-key-attempt"},
    )
    assert wrong_res.status_code == 401


def test_ttl_cache_accelerates_repeated_lookups() -> None:
    """Verify first request is a cache miss (`cached=False`) and second is a fast hit (`cached=True`)."""
    active_key = _reset_state()
    headers = {"X-API-Key": active_key}

    first = client.get("/api/v1/workshops/ws-101/summary", headers=headers)
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["cached"] is False
    assert first_data["workshop_id"] == "ws-101"

    second = client.get("/api/v1/workshops/ws-101/summary", headers=headers)
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["cached"] is True
    assert second_data["latency_ms"] < first_data["latency_ms"]


def test_rate_limiter_blocks_excess_burst_traffic() -> None:
    """Verify the token-bucket rate limiter returns 429 after capacity (5 requests) is exhausted."""
    active_key = _reset_state()
    headers = {"X-API-Key": active_key}

    status_codes: list[int] = []
    for _ in range(7):
        res = client.get("/api/v1/workshops/ws-101/summary", headers=headers)
        status_codes.append(res.status_code)

    assert status_codes[:5] == [200, 200, 200, 200, 200]
    assert 429 in status_codes[5:]


def test_multi_tiered_secret_resolution_file_and_production_guard() -> None:
    """Verify secret resolution reads from mounted secret file and fails closed in production."""
    original_env = os.environ.get("SERVICE_API_KEY")
    original_app_env = os.environ.get("APP_ENV")
    try:
        os.environ.pop("SERVICE_API_KEY", None)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write("mounted-secret-from-secret-manager\n")
            tmp_path = Path(tmp.name)

        resolved = resolve_service_api_key(secret_file_path=tmp_path)
        assert resolved == "mounted-secret-from-secret-manager"
        tmp_path.unlink(missing_ok=True)

        # In production mode with no env var and no file, it must fail closed
        os.environ["APP_ENV"] = "production"
        failed_closed = False
        try:
            resolve_service_api_key(secret_file_path="/nonexistent/secret.txt")
        except RuntimeError:
            failed_closed = True
        assert failed_closed is True
    finally:
        if original_env is not None:
            os.environ["SERVICE_API_KEY"] = original_env
        else:
            os.environ.pop("SERVICE_API_KEY", None)
        if original_app_env is not None:
            os.environ["APP_ENV"] = original_app_env
        else:
            os.environ.pop("APP_ENV", None)


def test_dependency_verifier_catches_slopsquatting_and_osv_vulns() -> None:
    """Verify the dependency scanner flags typosquatted, unapproved, and vulnerable packages."""
    clean_report = verify_dependencies_against_allowlist_and_osv(
        {"fastapi": "0.115.0", "pydantic": "2.9.0", "uvicorn": "0.30.0"}
    )
    assert clean_report.all_safe is True

    risky_report = verify_dependencies_against_allowlist_and_osv(
        {
            "fastpai": "0.115.0",          # Typosquat of fastapi
            "fastapi": "0.65.0",           # Known vulnerable version
            "magic-ai-helper": "1.0.0",    # Unapproved / hallucinated package
        }
    )
    assert risky_report.all_safe is False
    statuses = {f.package_name: f.status for f in risky_report.findings}
    assert statuses["fastpai"] == "typosquat_suspect"
    assert statuses["fastapi"] == "vulnerable"
    assert statuses["magic-ai-helper"] == "unapproved"


def test_before_and_after_security_optimization_and_scaling_demos() -> None:
    """Verify the beginner-friendly Before vs. After demos for security, caching, and scaling."""
    db = setup_sample_user_db()
    assert search_user_safe(db, "alice' OR '1'='1") == []
    assert len(search_user_safe(db, "alice")) == 1

    opt = run_optimization_comparison(num_visitors=30)
    assert opt["uncached_api_calls"] == 30
    assert opt["cached_api_calls"] == 1
    assert float(opt["speedup_factor"]) > 5.0

    scale = run_scaling_fairness_demo()
    assert scale["bot_accepted"] == 5
    assert scale["bot_blocked_with_429"] == 15
    assert scale["normal_users_served_200_ok"] == 3


if __name__ == "__main__":
    test_functions = [
        test_health_check_and_mandatory_security_headers,
        test_authentication_rejects_missing_or_wrong_api_key,
        test_ttl_cache_accelerates_repeated_lookups,
        test_rate_limiter_blocks_excess_burst_traffic,
        test_multi_tiered_secret_resolution_file_and_production_guard,
        test_dependency_verifier_catches_slopsquatting_and_osv_vulns,
        test_before_and_after_security_optimization_and_scaling_demos,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 09 tests passed!")

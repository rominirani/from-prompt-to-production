# Lab 09: Going Live on Google Cloud Run (Docker, Security, and Load Testing)

In this lab, we take a FastAPI backend and harden it for production deployment on **Google Cloud Run**.

## What You'll Learn

1. **Docker Containers 101 (`Dockerfile`)**: Packaging Python 3.12, `uv`, and a non-root `appuser` into a clean container image.
2. **Multi-Tiered Secret Resolution**: Loading API keys from environment variables or mounted **Google Cloud Secret Manager** files—failing closed in production if missing, and never hardcoding fallback strings in code.
3. **Stopping "Slopsquatting" & Vulnerable Packages**: Auditing dependencies (`verify_dependencies_against_allowlist_and_osv`) against an allowlist and known OSV advisories before building your container.
4. **API Hardening & Performance**: Constant-time API key checks (`secrets.compare_digest`), per-client token-bucket rate limiting (`429 Too Many Requests`), mandatory HTTP security headers, and an in-memory TTL cache verified with a `locustfile.py` load test.

## Files in This Lab

- `production_app.py` — The hardened FastAPI service, TTL cache, token-bucket rate limiter, multi-tiered secret resolver, and package auditor.
- `Dockerfile` — Production container definition using `python:3.12-slim`, `uv`, and a non-root user.
- `locustfile.py` — Load-testing script simulating concurrent user traffic against `/healthz` and `/api/v1/workshops/ws-101/summary`.
- `test_production_app.py` — Automated test suite verifying security headers, `401` auth enforcement, `429` rate limiting, TTL cache speedup, secret resolution, and dependency auditing.

## Running the Lab & Tests

From the repository root:

```bash
uv run python labs/lab09-cloud-run-deploy/test_production_app.py
```

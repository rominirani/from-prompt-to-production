# Lab 05: Building a Real Web Backend with a Database (`FastAPI` & SQL 101)

Welcome to **Lab 05**! In this lab, we build a **Workshop & Event Registration API** using **FastAPI**, **Pydantic v2**, and **SQLite** (`sqlite3`) that enforces seat capacity limits atomically, prevents duplicate registrations, blocks SQL injection with parameterized queries, and attaches strict HTTP security headers.

## What You'll Learn
- How HTTP methods (`GET`, `POST`), JSON payloads, and HTTP status codes (`200`, `201`, `404`, `409`, `422`) work together in a web API.
- How **FastAPI** uses Pydantic v2 models to validate incoming JSON and automatically generate interactive `/docs` (Swagger UI).
- Why string formatting (`f"SELECT ... {user_input}"`) causes **SQL Injection** vulnerabilities, and how parameterized queries (`?` placeholders) eliminate them.
- How relational database tables, primary keys, foreign keys, `UNIQUE` constraints, and **ACID transactions** prevent race conditions like overbooking a workshop.

## Files in This Lab
- `app.py` — FastAPI application, Pydantic v2 request/response models, security headers middleware, and parameterized SQLite database layer.
- `test_app.py` — Automated integration test suite using `fastapi.testclient.TestClient`.

## How to Run the Lab

Run the automated test suite from the repository root:

```bash
uv run python labs/lab05-fastapi-database/test_app.py
```

Or with `pytest`:

```bash
uv run pytest labs/lab05-fastapi-database/test_app.py
```

To run the local development server (bound safely to `127.0.0.1:8000`) and explore the interactive Swagger UI at `http://127.0.0.1:8000/docs`:

```bash
uv run python labs/lab05-fastapi-database/app.py
```

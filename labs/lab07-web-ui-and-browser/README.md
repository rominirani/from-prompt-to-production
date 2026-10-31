# Lab 07: From Sketch to Full-Stack Web App (and Testing It with Antigravity `/browser`)

In this lab, you build and test a full-stack **Smart Pantry & Recipe Tracker** web application in Python using **FastAPI**, server-rendered HTML with **HTMX** attributes (`hx-post`, `hx-target`, `hx-swap`), and **Google Gemini** (`google-genai`) structured recipe suggestions.

## What's Inside

- `pantry_app.py` — Full-stack FastAPI application with:
  - `GET /` — Renders the complete Smart Pantry dashboard with quoted HTML attributes and escaped values.
  - `POST /pantry/items` — Validates a new pantry ingredient with `Pydantic` v2, saves it using parameterized SQLite queries (`?`), flags low-stock items (`quantity <= reorder_threshold`), and returns an escaped HTML table row fragment for HTMX (`hx-target="#pantry-table-body"`).
  - `POST /pantry/recipes/suggest` — Generates a structured `RecipeSuggestion` using `google-genai` (or a deterministic offline fallback when `GEMINI_API_KEY` is not set) and renders a safe HTML card fragment (`hx-target="#recipe-result"`).
  - `GET /styles.css` — Serves a clean, modern stylesheet from `'self'` so our strict `Content-Security-Policy` never needs `'unsafe-inline'`.
  - Security middleware enforcing `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Permissions-Policy`.
- `test_pantry_app.py` — Automated test suite verifying dashboard rendering, HTMX fragment updates, low-stock badges, recipe generation, security headers, and Cross-Site Scripting (XSS) escaping.

## Running the App Locally

From the repository root (always binding to `127.0.0.1`):

```bash
uv run python labs/lab07-web-ui-and-browser/pantry_app.py
```

Then open `http://127.0.0.1:8007` in your browser or ask Antigravity to verify it using `/browser`.

## Running the Tests

```bash
uv run python labs/lab07-web-ui-and-browser/test_pantry_app.py
```

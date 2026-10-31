# Project Rules for Google Antigravity (`GEMINI.md`)

Welcome to the **From Prompt to Production with Python & Google AI** workspace!
Whenever you generate or edit code in this repository, please follow these project-wide rules:

## 1. Python & Tooling Standards
- **Python Version**: Target **Python 3.12+**. Always include type hints on function arguments and return values.
- **Package Manager**: Use `uv` (`uv run ...`, `uv add ...`). Never run global `pip install`.
- **Google AI SDK**: Always use the unified `google-genai` SDK (`from google import genai`). Do **not** use the legacy `google-generativeai` package.
- **Data Validation**: Use **Pydantic v2** (`BaseModel`, `Field`, `@field_validator`, `ConfigDict`) for all structured data, API payloads, and Gemini structured outputs.

## 2. Security & Reliability Rules
- **Secrets**: Never hardcode API keys, passwords, or tokens in source code. Load them from environment variables (`os.environ.get("GEMINI_API_KEY")`) or Google Cloud Secret Manager.
- **Database Queries**: Always use parameterized SQL queries (`?` placeholders or SQLAlchemy ORM/Core bindings). Never build SQL strings with f-strings or `+`.
- **Local Test Servers**: Bind local servers to `127.0.0.1` (never `0.0.0.0`) during local development and testing.
- **Web Output**: Always quote HTML attributes in templates and set standard security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy`).

## 3. Testing Habit
- Every lab folder (`labs/lab01-...` through `labs/lab10-...`) includes automated tests in `test_*.py`.
- Whenever you add or change a feature, run the tests before finishing your turn.

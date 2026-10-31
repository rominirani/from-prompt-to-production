# Project Coding Rules (`GEMINI.md`)

Whenever you generate or modify code inside `lab04-customizing-antigravity`, follow these non-negotiable standards:

## 1. Architecture & Separation of Concerns
- **Data Models (`src/study_tracker/models.py`)**: All data structures must be **Pydantic v2** `BaseModel` classes with `ConfigDict(str_strip_whitespace=True, frozen=True)` and explicit `Field(...)` bounds.
- **Business Logic (`src/study_tracker/service.py`)**: Keep all calculation, filtering, and formatting functions pure and deterministic. Never call `input()` or `print()` inside `service.py`—return structured models or formatted strings instead.
- **Tests (`tests/test_study_tracker.py`)**: Every new method in `StudyTrackerService` must have at least one happy-path test and one edge-case/validation test.

## 2. Python Style & Quality
- Target **Python 3.12+** and include explicit type hints on all function signatures (`def add_session(...) -> StudySession:`).
- Keep lines under 100 characters and follow `ruff` lint rules (`E`, `F`, `I`, `UP`, `B`).
- Never hardcode secrets or file paths specific to a single developer's machine.

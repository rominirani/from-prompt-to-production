---
name: add-study-command
description: >-
  Step-by-step workflow for adding a new study analytics query, filter, or report
  command to the study_tracker package. Use this skill whenever the user asks to
  add a new metric, summary calculation, or filtering feature to StudyTrackerService.
---

# Adding a New Study Tracker Command

Whenever you add a new analytics calculation or command to `study_tracker`, follow these 4 steps in exact order:

## Step 1: Check or Add Pydantic Output Models (`src/study_tracker/models.py`)
1. Open `src/study_tracker/models.py`.
2. If the new command returns structured data, define or update a `BaseModel` with `ConfigDict(str_strip_whitespace=True, frozen=True)` and explicit `Field(...)` constraints.
3. Export any new model in `src/study_tracker/__init__.py`.

## Step 2: Implement Pure Business Logic (`src/study_tracker/service.py`)
1. Add a well-typed method on `StudyTrackerService` (with full Python 3.12+ type hints).
2. Handle the **empty tracker edge case** (`len(self._sessions) == 0`) gracefully without raising a `ZeroDivisionError` or `ValueError`.
3. Do not use `print()`—return a Pydantic model, primitive value, or formatted string.

## Step 3: Write Happy-Path & Edge-Case Tests (`tests/test_study_tracker.py`)
1. Add a `test_<feature>_happy_path()` function verifying normal multi-session behavior.
2. Add a `test_<feature>_edge_cases()` function verifying empty state or invalid inputs.
3. Register both test functions in the `if __name__ == "__main__":` runner block at the bottom of `tests/test_study_tracker.py`.

## Step 4: Verify with the Test Runner
Run the test suite and confirm 100% pass rate before finishing your turn:
```bash
uv run python labs/lab04-customizing-antigravity/tests/test_study_tracker.py
```

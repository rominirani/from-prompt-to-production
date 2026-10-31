# Agent Operating Guide (`AGENTS.md`)

## Package Overview
`study_tracker` is a modular Python package for recording focused study sessions and computing topic-by-topic analytics.

- `src/study_tracker/models.py` — Validated Pydantic v2 models (`StudySession`, `TopicSummary`, `StudyProgressReport`).
- `src/study_tracker/service.py` — Core service (`StudyTrackerService`) for logging sessions, aggregating topic totals, and formatting Markdown reports.
- `tests/test_study_tracker.py` — Automated unit and edge-case tests.
- `.agents/skills/add-study-command/SKILL.md` — Step-by-step runbook for adding new study metrics or commands.

## How to Verify Changes
Always run the test suite after editing any `.py` file:
```bash
uv run python labs/lab04-customizing-antigravity/tests/test_study_tracker.py
```

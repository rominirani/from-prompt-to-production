# Lab 04: Teaching Antigravity How You Like to Work (`GEMINI.md`, Skills, and Hooks)

Welcome to **Lab 04**! In this lab, we transform a messy single-file script into a clean, modular Python package (`study_tracker`) and configure **Google Antigravity** with persistent rules (`GEMINI.md`, `AGENTS.md`), an on-demand workflow skill (`.agents/skills/add-study-command/SKILL.md`), and an automated lifecycle hook (`.agents/hooks.json`).

## Directory Structure
```text
lab04-customizing-antigravity/
├── GEMINI.md                                  # Always-on coding standards for Antigravity
├── AGENTS.md                                  # Quick project map and test commands
├── pyproject.toml                             # Project metadata, pytest, and ruff config
├── .agents/
│   ├── hooks.json                             # Automatic PostToolUse verification hook
│   └── skills/
│       └── add-study-command/
│           └── SKILL.md                       # On-demand skill for adding new analytics commands
├── src/
│   └── study_tracker/
│       ├── __init__.py                        # Clean package exports
│       ├── models.py                          # Pydantic v2 data models
│       └── service.py                         # Pure business logic & report formatting
└── tests/
    └── test_study_tracker.py                  # Automated pytest suite
```

## How to Run the Lab

From the repository root, run the automated test suite:

```bash
uv run python labs/lab04-customizing-antigravity/tests/test_study_tracker.py
```

Or with `pytest`:

```bash
uv run pytest labs/lab04-customizing-antigravity/tests/test_study_tracker.py
```

# Agent Operating Guide (`AGENTS.md`)

This file gives coding agents (Google Antigravity IDE, Antigravity 2.0, and the `agy` CLI) quick context on how this repository is organized.

## Repository Layout
- `chapters/` — The 10 step-by-step tutorial chapters written in plain, conversational English.
- `labs/` — The 10 self-contained, runnable Python labs (`lab01-ai-studio-basics` through `lab10-sdk-and-automation`).
- `.agents/skills/` — On-demand skills that teach the agent repeatable project workflows.
- `.agents/hooks.json` — Lifecycle hooks that automatically verify Python syntax and tests after edits.

## How to Run Any Lab's Tests
From the repository root:
```bash
uv run python labs/lab01-ai-studio-basics/test_receipt_extractor.py
```
Or if `pytest` is installed in your environment:
```bash
uv run pytest
```

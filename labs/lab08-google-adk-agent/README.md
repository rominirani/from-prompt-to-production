# Lab 08: Multi-Agent Event Concierge with Google ADK

In this lab, we build a **Multi-Agent Conference Concierge** using the **Google Agent Development Kit (`google-adk`)** and evaluate its tool-calling trajectories against a structured evaluation dataset (`eval_dataset.json`).

## What You'll Learn

1. **How Gemini Reads Your Python Tools**: Why type hints (`workshop_id: str`) and docstrings are the exact instructions the model uses to decide when and how to call your Python functions.
2. **Multi-Agent Delegation (`sub_agents`)**: How to split responsibilities between a `catalog_specialist` (searching sessions and checking seat counts) and a `booking_specialist` (verifying capacity and reserving seats) under a root `event_concierge_coordinator`.
3. **Agent Trajectory Evaluation**: How to grade an agent not just on its final words, but on the exact sequence of tools (`expected_tool_trajectory`) it called to get there.

## Files in This Lab

- `concierge_agent.py` — Defines the parameterized SQLite workshop store, the three ADK tool functions (`search_workshops`, `check_seat_availability`, `reserve_workshop_seat`), the multi-agent hierarchy (`root_agent`), and the trajectory evaluator (`evaluate_agent_trajectories`).
- `eval_dataset.json` — Four evaluation cases covering workshop discovery, seat availability checks, successful seat reservation, and capacity guardrail refusal when a workshop is full.
- `test_concierge_agent.py` — Automated test suite verifying the ADK agent hierarchy, tool execution, SQL injection protection, capacity guardrails, and 100% trajectory evaluation score.

## Running the Lab & Tests

From the repository root:

```bash
uv run python labs/lab08-google-adk-agent/concierge_agent.py
uv run python labs/lab08-google-adk-agent/test_concierge_agent.py
```

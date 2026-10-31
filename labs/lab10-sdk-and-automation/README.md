# Lab 10: Automating Your Workflow & Controlling Costs (Cloud Build, Vertex AI & Antigravity SDK)

In this final lab, we automate our testing and deployment pipeline with **Google Cloud Build**, optimize our **Gemini** token bill with smart model routing and caching, and run an automated code reviewer using the **`google-antigravity` Python SDK** pattern.

## What You'll Learn

1. **CI/CD with Google Cloud Build (`cloudbuild.yaml`)**: Automatically running your test suites, building your container image, and deploying to Cloud Run on every `git push`.
2. **Smart Model Routing & Cost Control**: Routing simple classification tasks to `gemini-3.1-flash-lite`, everyday agent tasks to `gemini-3-flash-preview`, and complex multi-file analysis to `gemini-3.1-pro-preview`, while calculating savings from **Gemini Context Caching** and the **Gemini Batch API** (50% discount).
3. **Programmatic Agents with the `google-antigravity` Python SDK**: Using `async with Agent(config) as agent:` to stream thoughts (`response.thoughts`), tool calls (`response.tool_calls`), and tokens in an automated pre-release diff reviewer.

## Files in This Lab

- `cloudbuild.yaml` — 4-step Google Cloud Build pipeline (test -> build -> push -> deploy).
- `automation_hub.py` — Implements the Gemini Cost & Model Router (`select_optimal_gemini_model`, `estimate_workload_cost`) and the async Antigravity SDK Diff Reviewer (`run_automated_diff_review`).
- `test_automation_hub.py` — Automated tests verifying model routing, Context Cache & Batch API savings, diff security checks, and `cloudbuild.yaml` structure.

## Running the Lab & Tests

From the repository root:

```bash
uv run python labs/lab10-sdk-and-automation/automation_hub.py
uv run python labs/lab10-sdk-and-automation/test_automation_hub.py
```

"""Automated tests for Lab 10: Cost Routing, CI/CD Config, and Antigravity SDK Automation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from automation_hub import (
    build_managed_agent_payload,
    estimate_workload_cost,
    run_automated_diff_review,
    select_optimal_gemini_model,
)


def test_smart_model_routing_Across_tiers() -> None:
    """Verify prompts route to Flash-Lite, Flash, or Pro based on task complexity."""
    lite_decision = select_optimal_gemini_model(
        "Classify the sentiment of this support ticket as positive or negative."
    )
    assert lite_decision.selected_model == "gemini-3.1-flash-lite"
    assert lite_decision.task_category == "classification_or_extraction"

    flash_decision = select_optimal_gemini_model(
        "Extract the customer's workshop booking request and call the reservation tool."
    )
    assert flash_decision.selected_model == "gemini-3-flash-preview"
    assert flash_decision.task_category == "general_agent_or_chat"

    pro_decision = select_optimal_gemini_model(
        "Perform a multi-file refactor and root-cause analysis of our distributed lock."
    )
    assert pro_decision.selected_model == "gemini-3.1-pro-preview"
    assert pro_decision.task_category == "deep_reasoning"


def test_context_cache_and_batch_cost_savings() -> None:
    """Verify Context Caching and Batch API significantly reduce workload token bills."""
    report = estimate_workload_cost(
        model_id="gemini-3-flash-preview",
        num_requests=1_000,
        shared_system_tokens=20_000,
        unique_user_tokens_per_req=500,
        output_tokens_per_req=250,
    )
    assert report.standard_cost_usd > report.cached_cost_usd
    assert report.cache_savings_percent > 60.0
    assert report.batch_cost_usd == round(report.standard_cost_usd * 0.50, 4)
    assert report.batch_savings_percent == 50.0


def test_antigravity_sdk_reviewer_blocks_unsafe_diff() -> None:
    """Verify the async SDK reviewer catches hardcoded fallback secrets and f-string SQL."""
    unsafe_diff = """
+++ b/app/db.py
+SECRET = os.environ.get("JWT_SECRET_KEY", "hardcoded-fallback")
+cursor.execute(f"SELECT * FROM users WHERE email = '{user_email}'")
+uvicorn.run(app, host="0.0.0.0", port=8000)
"""
    result = asyncio.run(run_automated_diff_review(unsafe_diff))
    assert result.approved is False
    rule_ids = {item.rule_id for item in result.findings}
    assert "SEC-001-HARDCODED-SECRET" in rule_ids
    assert "SEC-002-SQL-INJECTION" in rule_ids
    assert "SEC-003-WILDCARD-BIND" in rule_ids
    assert "static_diff_security_check" in result.tools_invoked
    assert len(result.thoughts_log) >= 2
    assert "STATUS: BLOCKED" in result.final_summary


def test_antigravity_sdk_reviewer_approves_clean_diff() -> None:
    """Verify a parameterized, secret-safe diff is approved cleanly."""
    clean_diff = """
+++ b/app/db.py
+cursor.execute("SELECT * FROM users WHERE email = ?", (user_email,))
+uvicorn.run(app, host="127.0.0.1", port=8000)
"""
    result = asyncio.run(run_automated_diff_review(clean_diff))
    assert result.approved is True
    assert result.findings == []
    assert "STATUS: APPROVED" in result.final_summary


def test_cloudbuild_yaml_is_valid_and_runs_tests_before_deploy() -> None:
    """Verify `cloudbuild.yaml` parses cleanly and runs tests before deploying to Cloud Run."""
    cb_path = Path(__file__).with_name("cloudbuild.yaml")
    data = yaml.safe_load(cb_path.read_text(encoding="utf-8"))
    steps = data.get("steps", [])
    step_ids = [step.get("id") for step in steps]
    assert step_ids == [
        "run-automated-tests",
        "build-container-image",
        "push-container-image",
        "deploy-to-cloud-run",
    ]


def test_build_managed_agent_payload() -> None:
    """Verify `build_managed_agent_payload` mounts Skill Registry skills into the Managed Agent definition."""
    payload = build_managed_agent_payload(
        display_name="Release Readiness Reviewer",
        project_id="my-gcp-project",
        skill_ids=["release-audit", "cost-guard"],
    )
    assert payload["displayName"] == "Release Readiness Reviewer"
    assert payload["definition"]["model"] == "gemini-3-flash-preview"
    tools = payload["definition"]["tools"]
    assert len(tools) == 4
    assert tools[2]["mount"]["path"] == "/.agent/skills/release-audit"
    assert (
        tools[2]["mount"]["source"]["skillSource"]["skillReference"]
        == "projects/my-gcp-project/locations/global/skills/release-audit"
    )


if __name__ == "__main__":
    test_functions = [
        test_smart_model_routing_Across_tiers,
        test_context_cache_and_batch_cost_savings,
        test_antigravity_sdk_reviewer_blocks_unsafe_diff,
        test_antigravity_sdk_reviewer_approves_clean_diff,
        test_cloudbuild_yaml_is_valid_and_runs_tests_before_deploy,
        test_build_managed_agent_payload,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 10 tests passed!")

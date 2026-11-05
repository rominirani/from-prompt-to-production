"""One-command verification runner for all 10 hands-on labs in the book.

Usage:
    uv run python run_all_labs.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

LAB_SUITES: list[tuple[str, str, str]] = [
    ("Lab 01", "AI Studio & Structured Receipts", "labs/lab01-ai-studio-basics/test_receipt_extractor.py"),
    ("Lab 02", "Antigravity Setup & Flashcard Quiz", "labs/lab02-antigravity-setup/test_flashcard_quiz.py"),
    ("Lab 03", "Pydantic & Penny-Exact Expense Splitter", "labs/lab03-data-and-tests/test_expense_splitter.py"),
    ("Lab 04", "Customizing Antigravity (Skills & Hooks)", "labs/lab04-customizing-antigravity/tests/test_study_tracker.py"),
    ("Lab 05", "FastAPI & SQL Workshop Backend", "labs/lab05-fastapi-database/test_app.py"),
    ("Lab 06", "FastMCP Live Event Inspector Server", "labs/lab06-mcp-tools/test_event_mcp_server.py"),
    ("Lab 07", "Full-Stack HTMX Smart Pantry & Security", "labs/lab07-web-ui-and-browser/test_pantry_app.py"),
    ("Lab 08", "Google ADK Multi-Agent Concierge & Eval", "labs/lab08-google-adk-agent/test_concierge_agent.py"),
    ("Lab 09", "Cloud Run Hardened Service & OSV Scanner", "labs/lab09-cloud-run-deploy/test_production_app.py"),
    ("Lab 10", "Gemini Cost Router & Antigravity SDK Bot", "labs/lab10-sdk-and-automation/test_automation_hub.py"),
    ("Blog Lab", "Context Layer (Cloud SQL + Knowledge Catalog + MCP Toolbox)", "blog-vibe-coding-meet-reality/test_context_layer_blog.py"),
]


def main() -> int:
    print("=" * 78)
    print(" From Prompt to Production with Python & Google AI — Full Lab Verification")
    print("=" * 78)

    results: list[tuple[str, str, bool, float, int]] = []
    overall_start = time.perf_counter()

    for lab_id, title, rel_path in LAB_SUITES:
        test_path = ROOT_DIR / rel_path
        test_dir = test_path.parent
        src_dir = test_dir.parent / "src"

        env = os.environ.copy()
        pythonpath_parts = [str(test_dir)]
        if src_dir.is_dir():
            pythonpath_parts.append(str(src_dir))
        if env.get("PYTHONPATH"):
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

        start = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(ROOT_DIR),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        pass_lines = [line for line in proc.stdout.splitlines() if "[PASS]" in line]
        passed = proc.returncode == 0
        results.append((lab_id, title, passed, elapsed_ms, len(pass_lines)))

        status_icon = "PASS" if passed else "FAIL"
        print(f"[{status_icon}] {lab_id}: {title:<42} ({len(pass_lines)} tests, {elapsed_ms:6.1f} ms)")
        if not passed:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)

    total_ms = (time.perf_counter() - overall_start) * 1000.0
    total_tests = sum(r[4] for r in results)
    all_passed = all(r[2] for r in results)

    print("-" * 78)
    print(
        f"Summary: {sum(1 for r in results if r[2])}/{len(results)} labs passed | "
        f"{total_tests} automated test suites verified in {total_ms:.0f} ms"
    )
    print("=" * 78)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

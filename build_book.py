"""Assemble the complete single-file edition (`BOOK.md`) from all chapters and the appendix.

Usage:
    uv run python build_book.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
CHAPTERS_DIR = ROOT_DIR / "chapters"
OUTPUT_PATH = ROOT_DIR / "BOOK.md"

CHAPTER_FILES: list[tuple[str, str, str]] = [
    (
        "Part 1: Getting Started — How Gemini Works & Setting Up Your Tools",
        "Chapter 1: How Gemini Actually Works (and Your First Steps in Google AI Studio)",
        "ch01-how-gemini-works-ai-studio.md",
    ),
    (
        "Part 1: Getting Started — How Gemini Works & Setting Up Your Tools",
        "Chapter 2: Setting Up Your Coding Setup From Scratch — Terminal, uv, Git, and Google Antigravity",
        "ch02-setting-up-your-coding-setup.md",
    ),
    (
        "Part 2: Writing Solid Code — Data Checks, Automated Tests, Rules & Web APIs",
        "Chapter 3: Stopping Bad Data and Catching Bugs Automatically (Pydantic & pytest 101)",
        "ch03-stopping-bad-data-and-testing.md",
    ),
    (
        "Part 2: Writing Solid Code — Data Checks, Automated Tests, Rules & Web APIs",
        "Chapter 4: Teaching Antigravity How You Like to Work (GEMINI.md, Skills, and Hooks)",
        "ch04-teaching-antigravity-your-rules.md",
    ),
    (
        "Part 2: Writing Solid Code — Data Checks, Automated Tests, Rules & Web APIs",
        "Chapter 5: Building a Real Web Backend with a Database (FastAPI & SQL 101)",
        "ch05-building-web-apis-and-databases.md",
    ),
    (
        "Part 3: Connecting Live Tools & Building Full-Stack Web Apps",
        "Chapter 6: Connecting Antigravity to Live Docs and Tools with MCP (Model Context Protocol)",
        "ch06-connecting-live-data-with-mcp.md",
    ),
    (
        "Part 3: Connecting Live Tools & Building Full-Stack Web Apps",
        "Chapter 7: From Sketch to Full-Stack Web App (and Testing It with Antigravity /browser)",
        "ch07-sketch-to-fullstack-web-app.md",
    ),
    (
        "Part 4: Building AI Agents with Google ADK, Deploying to Cloud Run & Automating Everything",
        "Chapter 8: Building Apps with Their Own AI Agents Using Google ADK (Agent Development Kit)",
        "ch08-building-agents-with-google-adk.md",
    ),
    (
        "Part 4: Building AI Agents with Google ADK, Deploying to Cloud Run & Automating Everything",
        "Chapter 9: Going Live on Google Cloud Run (Docker, Security Checks, and Load Testing 101)",
        "ch09-going-live-on-cloud-run.md",
    ),
    (
        "Part 4: Building AI Agents with Google ADK, Deploying to Cloud Run & Automating Everything",
        "Chapter 10: Automating Your Workflow & Controlling Costs (Cloud Build, Vertex AI, and the google-antigravity Python SDK)",
        "ch10-automating-with-antigravity-sdk.md",
    ),
    (
        "Bonus Reference",
        "Appendix: The AI Builder's Cheat Sheet, Tool Picker & Troubleshooting Guide",
        "appendix-cheatsheet-and-troubleshooting.md",
    ),
]


def _slugify_github_heading(title: str) -> str:
    """Create a GitHub-compatible markdown anchor slug from a heading."""
    cleaned = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"\s+", "-", cleaned.strip())


def _rewrite_chapter_links_for_root(text: str) -> str:
    """Rewrite `../labs/...` links to `./labs/...` and `./ch...` links to `./chapters/ch...`."""
    # Remove the per-chapter bottom navigation line since BOOK.md is a single continuous file
    lines = [
        line
        for line in text.splitlines()
        if not line.strip().startswith("**Navigation**:")
    ]
    joined = "\n".join(lines).strip()
    joined = joined.replace("](../labs/", "](./labs/")
    joined = joined.replace("](../README.md)", "](./README.md)")
    joined = re.sub(r"\]\(\./(ch\d+-[^)]+|appendix-[^)]+)\)", r"](./chapters/\1)", joined)
    return joined


def build_complete_book() -> Path:
    parts: list[str] = []
    parts.append("# From Prompt to Production with Python & Google AI\n")
    parts.append(
        "> **Complete Single-File Edition (`BOOK.md`)** — You can read the entire 10-chapter book "
        "and appendix right here on one page, or browse individual chapters in the "
        "[`chapters/`](./chapters/) directory and runnable Python labs in [`labs/`](./labs/).\n"
    )

    parts.append("## Table of Contents\n")
    current_part = ""
    for part_title, chapter_title, filename in CHAPTER_FILES:
        if part_title != current_part:
            current_part = part_title
            parts.append(f"\n### {current_part}\n")
        # Read actual H1 from the file so the anchor matches GitHub's exact heading slug
        raw_first_line = (CHAPTERS_DIR / filename).read_text(encoding="utf-8").splitlines()[0]
        h1_text = raw_first_line.lstrip("# ").strip()
        anchor = _slugify_github_heading(h1_text)
        parts.append(
            f"- [{h1_text}](#{anchor}) *(Individual file: [`chapters/{filename}`](./chapters/{filename}))*"
        )

    parts.append("\n---\n")

    for _, _, filename in CHAPTER_FILES:
        chapter_path = CHAPTERS_DIR / filename
        raw_content = chapter_path.read_text(encoding="utf-8")
        adjusted_content = _rewrite_chapter_links_for_root(raw_content)
        parts.append(adjusted_content)
        parts.append("\n\n---\n")

    final_markdown = "\n".join(parts).strip() + "\n"
    OUTPUT_PATH.write_text(final_markdown, encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    out = build_complete_book()
    line_count = len(out.read_text(encoding="utf-8").splitlines())
    print(f"Generated {out.name} ({line_count} lines)")

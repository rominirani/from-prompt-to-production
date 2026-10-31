# Lab 02: Study Flashcard & Quiz CLI App (`uv`, `.env`, Git & Antigravity Setup)

This lab accompanies [Chapter 2: Setting Up Your Coding Setup From Scratch — Terminal, `uv`, Git, and Google Antigravity](../../chapters/ch02-setting-up-your-coding-setup.md).

## What This Lab Demonstrates
1. Structuring a clean Python module managed by `uv` (`pyproject.toml`) and `.env` environment variables.
2. Generating structured `FlashcardDeck` objects with `google-genai` (`gemini-3-flash-preview`) with an automatic offline study deck fallback for local testing.
3. Saving and loading JSON decks safely on disk (protecting against `../` path traversal).
4. Grading user quiz answers with case-insensitive, whitespace-normalized comparison and calculating study scores.

## How to Run
From the repository root:

```bash
# Run the interactive demo
uv run python labs/lab02-antigravity-setup/flashcard_quiz.py

# Run the automated tests
uv run python labs/lab02-antigravity-setup/test_flashcard_quiz.py
```

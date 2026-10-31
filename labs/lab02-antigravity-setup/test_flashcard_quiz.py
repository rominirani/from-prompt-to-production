"""Automated tests for Chapter 2 Lab (`flashcard_quiz.py`).

Run with pytest:
    uv run pytest labs/lab02-antigravity-setup/test_flashcard_quiz.py
Or directly with Python:
    uv run python labs/lab02-antigravity-setup/test_flashcard_quiz.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from flashcard_quiz import (
    generate_flashcard_deck,
    grade_quiz_responses,
    load_deck_from_file,
    save_deck_to_file,
)


def test_generate_flashcard_deck_offline() -> None:
    """Offline flashcard generator returns the requested number of validated cards."""
    deck = generate_flashcard_deck("Python Project Setup", num_cards=3, force_offline=True)
    assert deck.topic == "Python Project Setup"
    assert len(deck.cards) == 3
    assert deck.cards[0].answer == ".env"


def test_grade_quiz_responses_perfect_and_partial_scores() -> None:
    """Quiz grader normalizes case/whitespace and accurately tracks missed questions."""
    deck = generate_flashcard_deck("Coding Basics", num_cards=4, force_offline=True)

    # Perfect score with mixed case and extra spaces
    perfect = grade_quiz_responses(deck, ["  .ENV ", "UV", "Git   Diff", "/PLAN"])
    assert perfect.correct_answers == 4
    assert perfect.score_percent == 100.0
    assert perfect.missed_questions == []

    # 3 out of 4 score
    partial = grade_quiz_responses(deck, [".env", "pip", "git diff", "/plan"])
    assert partial.correct_answers == 3
    assert partial.score_percent == 75.0
    assert len(partial.missed_questions) == 1


def test_save_and_load_deck_roundtrip() -> None:
    """Saving a deck to JSON and loading it back preserves all cards identically."""
    deck = generate_flashcard_deck("Git Checkpoints", num_cards=2, force_offline=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        saved_file = save_deck_to_file(deck, "git_deck", base_path)
        assert saved_file.name == "git_deck.json"
        loaded = load_deck_from_file("git_deck.json", base_path)
        assert loaded == deck


def test_path_traversal_is_rejected() -> None:
    """Attempting to save or load with '../' or subdirectories raises ValueError."""
    deck = generate_flashcard_deck("Security Check", num_cards=1, force_offline=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        for unsafe_name in ["../escape.json", "../../etc/passwd", "nested/deck.json"]:
            try:
                save_deck_to_file(deck, unsafe_name, base_path)
                raise AssertionError(f"Expected ValueError for unsafe filename: {unsafe_name}")
            except ValueError:
                pass


if __name__ == "__main__":
    test_functions = [
        test_generate_flashcard_deck_offline,
        test_grade_quiz_responses_perfect_and_partial_scores,
        test_save_and_load_deck_roundtrip,
        test_path_traversal_is_rejected,
    ]
    for fn in test_functions:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print(f"\nAll {len(test_functions)} tests in Lab 02 passed!")

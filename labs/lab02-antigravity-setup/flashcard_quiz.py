"""Chapter 2 Lab: Study Flashcard & Quiz App powered by Google Gemini (`google-genai`).

Demonstrates clean Python project structure, safe `.env` secret loading, structured
flashcard generation, safe local JSON storage, and deterministic quiz grading.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

FLASHCARD_SYSTEM_INSTRUCTION = (
    "You are an encouraging computer science tutor. Create clear, accurate study flashcards "
    "from the user's topic or notes. Keep answers concise (1 to 5 words when possible) so they "
    "can be graded easily in a quiz."
)


class Flashcard(BaseModel):
    """A single study flashcard."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, description="Clear study question")
    answer: str = Field(min_length=1, description="Concise, accurate answer")
    hint: str = Field(
        default="", description="Helpful hint that nudges the learner without giving away the answer"
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        default="medium", description="Difficulty level: easy, medium, or hard"
    )


class FlashcardDeck(BaseModel):
    """A collection of flashcards on a specific study topic."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, description="Title of the study topic")
    cards: list[Flashcard] = Field(min_length=1, description="List of study flashcards")


class QuizAttemptResult(BaseModel):
    """Summary of a learner's quiz run across a FlashcardDeck."""

    topic: str
    total_questions: int
    correct_answers: int
    score_percent: float
    missed_questions: list[str]


def _default_offline_deck(topic: str) -> FlashcardDeck:
    """Built-in starter deck used when running offline without a GEMINI_API_KEY."""
    return FlashcardDeck(
        topic=topic.strip(),
        cards=[
            Flashcard(
                question="Which file stores secret API keys locally so they are not hardcoded in Python?",
                answer=".env",
                hint="It starts with a dot and is short for environment.",
                difficulty="easy",
            ),
            Flashcard(
                question="Which modern Python tool creates a fast .venv virtual environment and manages pyproject.toml?",
                answer="uv",
                hint="A two-letter command-line tool.",
                difficulty="easy",
            ),
            Flashcard(
                question="Which Git command shows the exact line-by-line changes since your last save point?",
                answer="git diff",
                hint="Short for difference.",
                difficulty="medium",
            ),
            Flashcard(
                question="Which Google Antigravity slash command creates a step-by-step implementation blueprint before editing files?",
                answer="/plan",
                hint="Starts with a forward slash.",
                difficulty="easy",
            ),
        ],
    )


def generate_flashcard_deck(
    topic_or_notes: str,
    *,
    num_cards: int = 4,
    api_key: Optional[str] = None,
    model_name: str = "gemini-3-flash-preview",
    force_offline: bool = False,
) -> FlashcardDeck:
    """Generate a FlashcardDeck using Gemini Structured Outputs, or return the starter deck offline."""
    if not topic_or_notes or not topic_or_notes.strip():
        raise ValueError("topic_or_notes must not be empty.")
    if num_cards < 1 or num_cards > 25:
        raise ValueError("num_cards must be between 1 and 25.")

    resolved_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "").strip()
    if force_offline or not resolved_key or resolved_key == "your_gemini_api_key_here":
        deck = _default_offline_deck(topic_or_notes)
        return FlashcardDeck(topic=deck.topic, cards=deck.cards[:num_cards])

    client = genai.Client(api_key=resolved_key)
    prompt = f"Create exactly {num_cards} study flashcards for the following topic or notes:\n\n{topic_or_notes}"
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=FLASHCARD_SYSTEM_INSTRUCTION,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=FlashcardDeck,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return FlashcardDeck.model_validate_json(response.text)


def _resolve_safe_deck_path(filename: str, base_dir: Path) -> Path:
    """Resolve a deck filename strictly inside `base_dir` to prevent path traversal (`../`)."""
    if not filename or not filename.strip():
        raise ValueError("Deck filename must not be empty.")

    raw_name = filename.strip()
    clean_name = Path(raw_name).name
    if clean_name != raw_name or ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        raise ValueError(f"Unsafe deck filename rejected: {filename!r}")

    if not clean_name.endswith(".json"):
        clean_name = f"{clean_name}.json"

    resolved_base = base_dir.resolve()
    resolved_base.mkdir(parents=True, exist_ok=True)
    resolved_target = (resolved_base / clean_name).resolve()

    if resolved_target.parent != resolved_base:
        raise ValueError("Deck path escaped base directory boundary.")

    return resolved_target


def save_deck_to_file(deck: FlashcardDeck, filename: str, base_dir: Path) -> Path:
    """Save a FlashcardDeck as formatted JSON inside `base_dir`."""
    target_path = _resolve_safe_deck_path(filename, base_dir)
    target_path.write_text(deck.model_dump_json(indent=2), encoding="utf-8")
    return target_path


def load_deck_from_file(filename: str, base_dir: Path) -> FlashcardDeck:
    """Load and validate a FlashcardDeck from a JSON file inside `base_dir`."""
    target_path = _resolve_safe_deck_path(filename, base_dir)
    if not target_path.is_file():
        raise FileNotFoundError(f"Deck file not found: {target_path.name}")
    return FlashcardDeck.model_validate_json(target_path.read_text(encoding="utf-8"))


def normalize_answer(text: str) -> str:
    """Normalize a quiz answer for fair comparison (case-insensitive, trimmed)."""
    return " ".join(text.strip().lower().split())


def grade_quiz_responses(deck: FlashcardDeck, user_answers: list[str]) -> QuizAttemptResult:
    """Grade a list of user answers against a FlashcardDeck."""
    if len(user_answers) != len(deck.cards):
        raise ValueError(
            f"Expected {len(deck.cards)} answers, but received {len(user_answers)}."
        )

    correct_count = 0
    missed: list[str] = []

    for card, given in zip(deck.cards, user_answers):
        if normalize_answer(given) == normalize_answer(card.answer):
            correct_count += 1
        else:
            missed.append(card.question)

    total = len(deck.cards)
    score_pct = round((correct_count / total) * 100.0, 2)

    return QuizAttemptResult(
        topic=deck.topic,
        total_questions=total,
        correct_answers=correct_count,
        score_percent=score_pct,
        missed_questions=missed,
    )


if __name__ == "__main__":
    print("=== Chapter 2 Lab: Study Flashcard & Quiz App ===")
    study_deck = generate_flashcard_deck("Terminal, uv, Git & Google Antigravity Basics")
    print(f"Loaded Deck: '{study_deck.topic}' ({len(study_deck.cards)} cards)\n")
    for idx, card in enumerate(study_deck.cards, start=1):
        print(f"Card {idx} [{card.difficulty}]: {card.question}")
        print(f"  Hint:   {card.hint}")
        print(f"  Answer: {card.answer}\n")

    sample_user_answers = [".env", "uv", "git diff", "/plan"]
    result = grade_quiz_responses(study_deck, sample_user_answers)
    print(f"Quiz Result: {result.correct_answers}/{result.total_questions} ({result.score_percent}%)")

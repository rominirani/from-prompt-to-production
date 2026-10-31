"""Automated tests for Lab 04: Modular Study Session Tracker."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

# Ensure src/ is on sys.path when executed directly
LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from study_tracker import StudySession, StudyTrackerService


def test_add_and_validate_study_session() -> None:
    """Valid study sessions normalize whitespace and store clean attributes."""
    service = StudyTrackerService()
    session = service.add_session(
        topic="  Pydantic   Validation  ",
        duration_minutes=45,
        difficulty_rating=4,
        notes="  Built custom field validators  ",
    )
    assert isinstance(session, StudySession)
    assert session.topic == "Pydantic Validation"
    assert session.duration_minutes == 45
    assert session.difficulty_rating == 4
    assert session.notes == "Built custom field validators"


def test_rejects_invalid_duration_and_difficulty_and_blank_topic() -> None:
    """Out-of-range durations, bad difficulty ratings, or blank topics raise ValidationError."""
    service = StudyTrackerService()

    invalid_inputs = [
        {"topic": "   ", "duration_minutes": 30, "difficulty_rating": 3},
        {"topic": "A", "duration_minutes": 30, "difficulty_rating": 3},
        {"topic": "FastAPI", "duration_minutes": 0, "difficulty_rating": 3},
        {"topic": "FastAPI", "duration_minutes": 600, "difficulty_rating": 3},
        {"topic": "FastAPI", "duration_minutes": 30, "difficulty_rating": 6},
    ]

    for bad in invalid_inputs:
        try:
            service.add_session(**bad)  # type: ignore[arg-type]
            raise AssertionError(f"Expected ValidationError for {bad!r}")
        except ValidationError:
            pass


def test_progress_report_aggregates_and_sorts_topics_correctly() -> None:
    """Topics are grouped case-insensitively and sorted by total minutes descending."""
    service = StudyTrackerService()
    service.add_session(topic="Python Type Hints", duration_minutes=30, difficulty_rating=2)
    service.add_session(topic="FastAPI & SQL", duration_minutes=50, difficulty_rating=4)
    service.add_session(topic="fastapi & sql", duration_minutes=40, difficulty_rating=5)

    report = service.build_progress_report()
    assert report.total_sessions == 3
    assert report.total_minutes == 120
    assert report.top_topic == "FastAPI & SQL"
    assert len(report.topic_summaries) == 2

    first_summary = report.topic_summaries[0]
    assert first_summary.topic == "FastAPI & SQL"
    assert first_summary.session_count == 2
    assert first_summary.total_minutes == 90
    assert first_summary.average_difficulty == 4.5


def test_empty_tracker_returns_safe_report_and_markdown() -> None:
    """Calling build_progress_report or format_markdown_report with 0 sessions never crashes."""
    service = StudyTrackerService()
    report = service.build_progress_report()
    assert report.total_sessions == 0
    assert report.total_minutes == 0
    assert report.top_topic is None
    assert report.topic_summaries == []

    md = service.format_markdown_report()
    assert "No study sessions logged yet." in md


def test_list_sessions_with_case_insensitive_filter() -> None:
    """Filtering by topic returns matching sessions regardless of casing or extra spaces."""
    service = StudyTrackerService()
    service.add_session(topic="Antigravity Skills", duration_minutes=25)
    service.add_session(topic="Pytest Basics", duration_minutes=35)
    service.add_session(topic="  antigravity   skills ", duration_minutes=40)

    filtered = service.list_sessions(topic_filter="ANTIGRAVITY SKILLS")
    assert len(filtered) == 2
    assert sum(s.duration_minutes for s in filtered) == 65


if __name__ == "__main__":
    test_functions = [
        test_add_and_validate_study_session,
        test_rejects_invalid_duration_and_difficulty_and_blank_topic,
        test_progress_report_aggregates_and_sorts_topics_correctly,
        test_empty_tracker_returns_safe_report_and_markdown,
        test_list_sessions_with_case_insensitive_filter,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 04 tests passed!")

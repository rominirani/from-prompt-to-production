"""Core business logic and report formatting for the Study Session Tracker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from study_tracker.models import (
    SkillCatalogEntry,
    StudyProgressReport,
    StudySession,
    TopicSummary,
)


class StudyTrackerService:
    """Manages study sessions and computes topic-by-topic progress analytics."""

    def __init__(self) -> None:
        self._sessions: list[StudySession] = []

    def add_session(
        self,
        topic: str,
        duration_minutes: int,
        difficulty_rating: int = 3,
        notes: str = "",
    ) -> StudySession:
        """Validate and record a new study session."""
        session = StudySession(
            topic=topic,
            duration_minutes=duration_minutes,
            difficulty_rating=difficulty_rating,
            notes=notes,
        )
        self._sessions.append(session)
        return session

    def list_sessions(self, topic_filter: str | None = None) -> list[StudySession]:
        """Return all logged sessions, optionally filtered case-insensitively by topic."""
        if topic_filter is None:
            return list(self._sessions)
        target = " ".join(topic_filter.strip().split()).lower()
        return [s for s in self._sessions if s.topic.lower() == target]

    def build_progress_report(self) -> StudyProgressReport:
        """Aggregate sessions by topic and identify the most-studied subject."""
        if not self._sessions:
            return StudyProgressReport(
                total_sessions=0,
                total_minutes=0,
                top_topic=None,
                topic_summaries=[],
            )

        grouped: dict[str, list[StudySession]] = {}
        canonical_names: dict[str, str] = {}

        for session in self._sessions:
            key = session.topic.lower()
            if key not in grouped:
                grouped[key] = []
                canonical_names[key] = session.topic
            grouped[key].append(session)

        summaries: list[TopicSummary] = []
        for key, items in grouped.items():
            total_mins = sum(item.duration_minutes for item in items)
            avg_diff = round(
                sum(item.difficulty_rating for item in items) / len(items), 2
            )
            summaries.append(
                TopicSummary(
                    topic=canonical_names[key],
                    session_count=len(items),
                    total_minutes=total_mins,
                    average_difficulty=avg_diff,
                )
            )

        # Sort by total_minutes descending, then alphabetically by topic name
        summaries.sort(key=lambda item: (-item.total_minutes, item.topic.lower()))

        overall_minutes = sum(item.total_minutes for item in summaries)
        top_topic_name = summaries[0].topic if summaries else None

        return StudyProgressReport(
            total_sessions=len(self._sessions),
            total_minutes=overall_minutes,
            top_topic=top_topic_name,
            topic_summaries=summaries,
        )

    def format_markdown_report(self) -> str:
        """Render the current progress report as a clean Markdown summary."""
        report = self.build_progress_report()
        if report.total_sessions == 0:
            return "# Study Progress Report\n\nNo study sessions logged yet."

        lines = [
            "# Study Progress Report",
            "",
            f"- **Total Sessions**: {report.total_sessions}",
            f"- **Total Study Time**: {report.total_minutes} mins",
            f"- **Top Topic**: {report.top_topic}",
            "",
            "## Breakdown by Topic",
        ]
        for summary in report.topic_summaries:
            lines.append(
                f"- **{summary.topic}**: {summary.total_minutes} mins "
                f"({summary.session_count} sessions, avg difficulty {summary.average_difficulty}/5.0)"
            )
        return "\n".join(lines)


def parse_skill_frontmatter(skill_md_path: str | Path) -> SkillCatalogEntry:
    """Read only the YAML frontmatter (`name` and `description`) from a `SKILL.md` file."""
    resolved = Path(skill_md_path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Skill file not found: {resolved}")

    raw_text = resolved.read_text(encoding="utf-8")
    if not raw_text.startswith("---"):
        raise ValueError(f"Skill file {resolved.name} is missing YAML frontmatter '---'.")

    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Skill file {resolved.name} has unclosed YAML frontmatter.")

    parsed = yaml.safe_load(parts[1]) or {}
    return SkillCatalogEntry(
        name=str(parsed.get("name", "")).strip(),
        description=" ".join(str(parsed.get("description", "")).split()),
        skill_path=str(resolved),
    )


def build_runtime_skill_mount(
    skill_name: str,
    *,
    project_id: str,
    location: str = "global",
) -> dict[str, Any]:
    """Build a Managed Agents API / runtime skill mount block pointing to Google Cloud Skill Registry."""
    cleaned_name = skill_name.strip().lower()
    if not cleaned_name:
        raise ValueError("skill_name must not be empty.")
    return {
        "mount": {
            "path": f"/.agent/skills/{cleaned_name}",
            "source": {
                "skillSource": {
                    "skillReference": f"projects/{project_id}/locations/{location}/skills/{cleaned_name}"
                }
            },
        }
    }

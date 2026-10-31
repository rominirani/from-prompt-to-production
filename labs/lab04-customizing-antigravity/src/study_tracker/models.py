"""Validated Pydantic v2 models for the Study Session Tracker."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudySession(BaseModel):
    """A single focused study block logged by a learner."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    topic: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Subject studied (e.g., 'Pydantic Validation', 'FastAPI Routes').",
    )
    duration_minutes: int = Field(
        ...,
        ge=1,
        le=480,
        description="Length of the study session in minutes (1 to 480).",
    )
    difficulty_rating: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Self-rated difficulty from 1 (easy) to 5 (challenging).",
    )
    notes: str = Field(
        default="",
        max_length=280,
        description="Optional short reflection on what was learned.",
    )

    @field_validator("topic")
    @classmethod
    def normalize_topic_title(cls, value: str) -> str:
        """Ensure topic is not blank and collapse repeated internal spaces."""
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Topic must contain at least 2 non-whitespace characters.")
        return cleaned


class TopicSummary(BaseModel):
    """Aggregated study totals for a single topic."""

    model_config = ConfigDict(frozen=True)

    topic: str
    session_count: int = Field(..., ge=1)
    total_minutes: int = Field(..., ge=1)
    average_difficulty: float = Field(..., ge=1.0, le=5.0)


class StudyProgressReport(BaseModel):
    """Overall study report across all logged sessions."""

    model_config = ConfigDict(frozen=True)

    total_sessions: int = Field(..., ge=0)
    total_minutes: int = Field(..., ge=0)
    top_topic: str | None = None
    topic_summaries: list[TopicSummary] = Field(default_factory=list)


class SkillCatalogEntry(BaseModel):
    """Parsed YAML frontmatter metadata from a `SKILL.md` file (progressive disclosure)."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    skill_path: str = Field(..., min_length=1)

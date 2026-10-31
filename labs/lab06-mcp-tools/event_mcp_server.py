"""Lab 06: Read-Only Event & Workshop MCP Server for Google Antigravity.

This module exposes safe, read-only Model Context Protocol (MCP) tools so
Antigravity can inspect our developer workshop database and format official
Google Developer Knowledge lookups without guessing schemas or exposing raw PII.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Support both mcp 2.x (MCPServer) and mcp 1.x (FastMCP) seamlessly
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]


WORKSHOP_ID_PATTERN = re.compile(r"^ws-[a-z0-9-]{2,32}$")
ALLOWED_STATUSES = {"CONFIRMED", "WAITLISTED", "CANCELLED"}


def mask_email(email: str) -> str:
    """Mask an email address so raw attendee PII is never exposed to the model."""
    cleaned = email.strip()
    if "@" not in cleaned:
        return "***"
    local_part, domain_part = cleaned.split("@", 1)
    if len(local_part) <= 2:
        masked_local = f"{local_part[:1]}***"
    else:
        masked_local = f"{local_part[:2]}***"
    return f"{masked_local}@{domain_part}"


class WorkshopFilterInput(BaseModel):
    """Validated filter parameters for listing workshops."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic_filter: str = Field(
        default="",
        max_length=50,
        description="Optional keyword filter matched against workshop title or topic.",
    )
    only_open_seats: bool = Field(
        default=False,
        description="When True, only return workshops that still have open seats.",
    )


class WorkshopIdInput(BaseModel):
    """Validated workshop identifier."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    workshop_id: str = Field(
        ...,
        min_length=5,
        max_length=35,
        description="Unique workshop ID such as 'ws-genai-101'.",
    )

    @field_validator("workshop_id")
    @classmethod
    def validate_workshop_id(cls, value: str) -> str:
        normalized = value.lower()
        if not WORKSHOP_ID_PATTERN.match(normalized):
            raise ValueError(
                "workshop_id must match pattern 'ws-<slug>' using lowercase letters, digits, or hyphens."
            )
        return normalized


class RegistrationSearchInput(WorkshopIdInput):
    """Validated parameters for searching workshop registrations."""

    status_filter: str = Field(
        default="CONFIRMED",
        description="Registration status filter: CONFIRMED, WAITLISTED, or CANCELLED.",
    )

    @field_validator("status_filter")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ALLOWED_STATUSES:
            raise ValueError(
                f"status_filter must be one of {sorted(ALLOWED_STATUSES)}."
            )
        return normalized


class DeveloperKnowledgeLookupInput(BaseModel):
    """Validated parameters for formatting a Google Developer Knowledge lookup."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(
        ...,
        min_length=3,
        max_length=240,
        description="Focused search keywords, natural-language question, or document path.",
    )
    mode: Literal["search_documents", "answer_query", "get_documents"] = Field(
        default="search_documents",
        description="Which Developer Knowledge MCP tool to format the request for.",
    )


def create_sample_workshop_db(db_path: str | Path) -> Path:
    """Create and seed a sample SQLite database of Google AI developer workshops."""
    resolved_path = Path(db_path).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(resolved_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workshops (
                workshop_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                instructor TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                seats_taken INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id TEXT NOT NULL,
                attendee_name TEXT NOT NULL,
                attendee_email TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (workshop_id) REFERENCES workshops (workshop_id)
            )
            """
        )

        # Clear any existing rows so seeding is deterministic for tests
        conn.execute("DELETE FROM registrations")
        conn.execute("DELETE FROM workshops")

        workshops = [
            (
                "ws-genai-101",
                "Structured Outputs with google-genai and Pydantic",
                "Gemini SDK",
                "Romin Irani",
                "2025-05-12T10:00:00Z",
                30,
                24,
            ),
            (
                "ws-cloudrun-201",
                "Deploying FastAPI AI Microservices to Cloud Run",
                "Cloud Run",
                "Priya Desai",
                "2025-05-14T14:00:00Z",
                25,
                25,
            ),
            (
                "ws-mcp-301",
                "Building Custom MCP Servers for Google Antigravity",
                "MCP & Agents",
                "Romin Irani",
                "2025-05-16T16:00:00Z",
                40,
                31,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO workshops (
                workshop_id, title, topic, instructor, starts_at, capacity, seats_taken
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            workshops,
        )

        registrations = [
            (
                "ws-genai-101",
                "Aarav Mehta",
                "aarav.mehta@example.org",
                "Backend Developer",
                "CONFIRMED",
            ),
            (
                "ws-genai-101",
                "Elena Rostova",
                "elena.rostova@example.org",
                "Data Scientist",
                "CONFIRMED",
            ),
            (
                "ws-cloudrun-201",
                "Marcus Vance",
                "marcus.vance@example.com",
                "Platform Engineer",
                "CONFIRMED",
            ),
            (
                "ws-cloudrun-201",
                "Sana Khan",
                "sana.khan@example.com",
                "Full-Stack Engineer",
                "WAITLISTED",
            ),
            (
                "ws-mcp-301",
                "Devon Brooks",
                "devon.brooks@example.net",
                "AI Engineer",
                "CONFIRMED",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO registrations (
                workshop_id, attendee_name, attendee_email, role, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            registrations,
        )
        conn.commit()

    return resolved_path


def _resolve_db_path() -> Path:
    """Resolve the active SQLite database path, seeding a default file if needed."""
    configured = os.environ.get("WORKSHOP_DB_PATH")
    if configured:
        path = Path(configured).resolve()
        if not path.exists():
            create_sample_workshop_db(path)
        return path

    default_path = Path(tempfile.gettempdir()) / "prompt_to_prod_lab06_workshops.db"
    if not default_path.exists():
        create_sample_workshop_db(default_path)
    return default_path


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection in strict read-only URI mode."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# Instantiate the MCP server
mcp = FastMCP("workshop-event-inspector")


@mcp.tool()
def list_upcoming_workshops(
    topic_filter: str = "",
    only_open_seats: bool = False,
) -> list[dict[str, Any]]:
    """List scheduled developer workshops with optional topic and open-seat filters."""
    validated = WorkshopFilterInput(
        topic_filter=topic_filter,
        only_open_seats=only_open_seats,
    )
    db_path = _resolve_db_path()

    query = """
        SELECT
            workshop_id,
            title,
            topic,
            instructor,
            starts_at,
            capacity,
            seats_taken,
            (capacity - seats_taken) AS seats_remaining
        FROM workshops
        WHERE (? = '' OR LOWER(title) LIKE ? OR LOWER(topic) LIKE ?)
          AND (? = 0 OR seats_taken < capacity)
        ORDER BY starts_at ASC
    """
    like_pattern = f"%{validated.topic_filter.lower()}%"
    open_flag = 1 if validated.only_open_seats else 0

    with _connect_readonly(db_path) as conn:
        rows = conn.execute(
            query,
            (validated.topic_filter, like_pattern, like_pattern, open_flag),
        ).fetchall()

    return [
        {
            "workshop_id": row["workshop_id"],
            "title": row["title"],
            "topic": row["topic"],
            "instructor": row["instructor"],
            "starts_at": row["starts_at"],
            "capacity": int(row["capacity"]),
            "seats_taken": int(row["seats_taken"]),
            "seats_remaining": int(row["seats_remaining"]),
            "is_full": int(row["seats_remaining"]) <= 0,
        }
        for row in rows
    ]


@mcp.tool()
def check_workshop_seat_status(workshop_id: str) -> dict[str, Any]:
    """Return capacity, remaining seats, and waitlist count for a workshop ID."""
    validated = WorkshopIdInput(workshop_id=workshop_id)
    db_path = _resolve_db_path()

    with _connect_readonly(db_path) as conn:
        workshop_row = conn.execute(
            """
            SELECT workshop_id, title, capacity, seats_taken
            FROM workshops
            WHERE workshop_id = ?
            """,
            (validated.workshop_id,),
        ).fetchone()

        if workshop_row is None:
            return {
                "found": False,
                "workshop_id": validated.workshop_id,
                "message": f"No workshop found with ID '{validated.workshop_id}'.",
            }

        waitlist_row = conn.execute(
            """
            SELECT COUNT(*) AS waitlisted_count
            FROM registrations
            WHERE workshop_id = ? AND status = 'WAITLISTED'
            """,
            (validated.workshop_id,),
        ).fetchone()

    capacity = int(workshop_row["capacity"])
    seats_taken = int(workshop_row["seats_taken"])
    seats_remaining = max(0, capacity - seats_taken)
    waitlisted_count = int(waitlist_row["waitlisted_count"]) if waitlist_row else 0

    if seats_remaining == 0:
        availability_badge = "FULL_WAITLIST_ACTIVE"
    elif seats_remaining <= 5:
        availability_badge = "ALMOST_FULL"
    else:
        availability_badge = "OPEN"

    return {
        "found": True,
        "workshop_id": workshop_row["workshop_id"],
        "title": workshop_row["title"],
        "capacity": capacity,
        "seats_taken": seats_taken,
        "seats_remaining": seats_remaining,
        "waitlisted_count": waitlisted_count,
        "availability_badge": availability_badge,
    }


@mcp.tool()
def search_registrations_by_workshop(
    workshop_id: str,
    status_filter: str = "CONFIRMED",
) -> list[dict[str, Any]]:
    """List registrations for a workshop with attendee email addresses masked."""
    validated = RegistrationSearchInput(
        workshop_id=workshop_id,
        status_filter=status_filter,
    )
    db_path = _resolve_db_path()

    with _connect_readonly(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                registration_id,
                workshop_id,
                attendee_name,
                attendee_email,
                role,
                status
            FROM registrations
            WHERE workshop_id = ? AND status = ?
            ORDER BY registration_id ASC
            """,
            (validated.workshop_id, validated.status_filter),
        ).fetchall()

    return [
        {
            "registration_id": int(row["registration_id"]),
            "workshop_id": row["workshop_id"],
            "attendee_name": row["attendee_name"],
            "attendee_email_masked": mask_email(row["attendee_email"]),
            "role": row["role"],
            "status": row["status"],
        }
        for row in rows
    ]


@mcp.tool()
def build_developer_knowledge_lookup(
    query: str,
    mode: str = "search_documents",
) -> dict[str, Any]:
    """Format an official Google Developer Knowledge MCP tool request and REST fallback."""
    validated = DeveloperKnowledgeLookupInput(query=query, mode=mode)  # type: ignore[arg-type]

    server_name = "google-cloud-developer_developer-knowledge"
    if validated.mode == "search_documents":
        mcp_arguments: dict[str, Any] = {"query": validated.query}
        rest_endpoint = (
            "https://developerknowledge.googleapis.com/v1/documents:searchDocumentChunks"
        )
        http_method = "GET"
    elif validated.mode == "answer_query":
        mcp_arguments = {"query": validated.query}
        rest_endpoint = "https://developerknowledge.googleapis.com/v1:answerQuery"
        http_method = "POST"
    else:
        normalized_doc = validated.query.removeprefix("https://").removeprefix("http://")
        if not normalized_doc.startswith("documents/"):
            normalized_doc = f"documents/{normalized_doc}"
        mcp_arguments = {"names": [normalized_doc]}
        rest_endpoint = f"https://developerknowledge.googleapis.com/v1/{normalized_doc}"
        http_method = "GET"

    return {
        "server_name": server_name,
        "tool_name": validated.mode,
        "mcp_arguments": mcp_arguments,
        "rest_fallback": {
            "method": http_method,
            "endpoint": rest_endpoint,
            "auth_header_hint": "Authorization: Bearer $(gcloud auth print-access-token)",
        },
    }


def list_registered_tool_names() -> list[str]:
    """Return the names of all tools registered on the MCP server."""
    if hasattr(mcp, "_tool_manager"):
        return [tool.name for tool in mcp._tool_manager.list_tools()]
    return [
        "list_upcoming_workshops",
        "check_workshop_seat_status",
        "search_registrations_by_workshop",
        "build_developer_knowledge_lookup",
    ]


if __name__ == "__main__":
    # When launched by Antigravity via Stdio transport, run the MCP loop
    mcp.run()

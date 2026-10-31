"""Lab 08: Multi-Agent Event Concierge built with Google ADK.

Demonstrates:
1. Defining Python tool functions with clear type hints and docstrings so Gemini
   knows when and how to call them.
2. Using parameterized SQLite queries inside agent tools to prevent SQL injection.
3. Organizing specialist agents (`catalog_specialist`, `booking_specialist`) under
   a root coordinator (`event_concierge_coordinator`) with `google.adk.agents.Agent`.
4. Evaluating tool-calling trajectories against an evaluation dataset (`eval_dataset.json`).
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# 1. Pydantic v2 Data Models
# ---------------------------------------------------------------------------


class WorkshopInfo(BaseModel):
    """Structured metadata about a conference workshop."""

    model_config = ConfigDict(extra="forbid")

    workshop_id: str = Field(description="Unique identifier such as ws-101")
    title: str = Field(description="Human-readable workshop title")
    topic: str = Field(description="Primary topic tag (e.g., python, agents, cloud-run)")
    room: str = Field(description="Room name in the conference venue")
    capacity: int = Field(ge=1, description="Maximum seats in the room")
    booked_seats: int = Field(ge=0, description="Number of currently reserved seats")

    @property
    def seats_remaining(self) -> int:
        """Calculate open seats remaining."""
        return max(0, self.capacity - self.booked_seats)


class ToolCallRecord(BaseModel):
    """Records a single tool invocation made during an agent turn."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any]
    output: dict[str, Any]


class AgentTurnTrace(BaseModel):
    """Captures the full trajectory of an agent handling a user prompt."""

    model_config = ConfigDict(extra="forbid")

    user_prompt: str
    delegated_agent: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    final_response: str

    @property
    def tool_trajectory(self) -> list[str]:
        """Ordered list of tool names called during the turn."""
        return [call.tool_name for call in self.tool_calls]


class EvalCaseResult(BaseModel):
    """Grading result for a single evaluation dataset case."""

    model_config = ConfigDict(extra="forbid")

    eval_case_id: str
    delegate_matched: bool
    trajectory_matched: bool
    keywords_matched: bool
    actual_trajectory: list[str]
    expected_trajectory: list[str]
    final_response: str

    @property
    def passed(self) -> bool:
        """A case passes only if delegate, tool trajectory, and response keywords match."""
        return self.delegate_matched and self.trajectory_matched and self.keywords_matched


class EvalSummaryReport(BaseModel):
    """Aggregated evaluation scorecard across all cases in eval_dataset.json."""

    model_config = ConfigDict(extra="forbid")

    total_cases: int
    passed_cases: int
    trajectory_accuracy: float
    results: list[EvalCaseResult]

    @field_validator("trajectory_accuracy")
    @classmethod
    def validate_accuracy_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("trajectory_accuracy must be between 0.0 and 1.0")
        return round(value, 4)


# ---------------------------------------------------------------------------
# 2. Parameterized SQLite Workshop Store
# ---------------------------------------------------------------------------

_DB_CONNECTION: sqlite3.Connection | None = None

INITIAL_WORKSHOPS: list[tuple[str, str, str, str, int, int]] = [
    ("ws-101", "Build Fast APIs with Gemini & Python", "python", "Room A", 30, 28),
    ("ws-102", "Hands-On Google ADK Agents", "agents", "Room B", 25, 25),
    ("ws-103", "Deploying Containers to Cloud Run", "cloud-run", "Room C", 40, 15),
]


def get_db_connection() -> sqlite3.Connection:
    """Return a shared in-memory SQLite connection seeded with workshop data."""
    global _DB_CONNECTION
    if _DB_CONNECTION is None:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _initialize_schema(conn)
        _DB_CONNECTION = conn
    return _DB_CONNECTION


def reset_workshop_store() -> None:
    """Reset the in-memory database to its initial state for repeatable tests."""
    global _DB_CONNECTION
    if _DB_CONNECTION is not None:
        _DB_CONNECTION.close()
        _DB_CONNECTION = None
    get_db_connection()


def _initialize_schema(conn: sqlite3.Connection) -> None:
    """Create tables and seed initial conference workshops using parameterized SQL."""
    with conn:
        conn.execute(
            """
            CREATE TABLE workshops (
                workshop_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                room TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                booked_seats INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE reservations (
                reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id TEXT NOT NULL,
                attendee_name TEXT NOT NULL,
                attendee_email TEXT NOT NULL,
                UNIQUE(workshop_id, attendee_email)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO workshops (workshop_id, title, topic, room, capacity, booked_seats)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            INITIAL_WORKSHOPS,
        )


# ---------------------------------------------------------------------------
# 3. ADK Tool Functions (Type Hints + Docstrings = Gemini's Tool Manual)
# ---------------------------------------------------------------------------


def search_workshops(topic: str = "") -> dict[str, Any]:
    """Searches conference workshops by topic or keyword.

    Use this tool when an attendee asks what workshops are available or looks
    for sessions on a specific subject like 'python', 'agents', or 'cloud-run'.

    Args:
        topic: Topic keyword to filter workshops (for example, 'python' or 'agents').
               Pass an empty string to list all workshops.

    Returns:
        A dictionary containing 'status', 'count', and a 'workshops' list.
    """
    conn = get_db_connection()
    cleaned_topic = topic.strip().lower()

    if cleaned_topic:
        like_pattern = f"%{cleaned_topic}%"
        cursor = conn.execute(
            """
            SELECT workshop_id, title, topic, room, capacity, booked_seats
            FROM workshops
            WHERE LOWER(topic) LIKE ? OR LOWER(title) LIKE ?
            ORDER BY workshop_id ASC
            """,
            (like_pattern, like_pattern),
        )
    else:
        cursor = conn.execute(
            """
            SELECT workshop_id, title, topic, room, capacity, booked_seats
            FROM workshops
            ORDER BY workshop_id ASC
            """
        )

    workshops: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        info = WorkshopInfo(
            workshop_id=row["workshop_id"],
            title=row["title"],
            topic=row["topic"],
            room=row["room"],
            capacity=row["capacity"],
            booked_seats=row["booked_seats"],
        )
        workshops.append(
            {
                "workshop_id": info.workshop_id,
                "title": info.title,
                "topic": info.topic,
                "room": info.room,
                "seats_remaining": info.seats_remaining,
            }
        )

    return {
        "status": "success",
        "query_topic": cleaned_topic or "all",
        "count": len(workshops),
        "workshops": workshops,
    }


def check_seat_availability(workshop_id: str) -> dict[str, Any]:
    """Checks the current seat availability for a specific workshop ID.

    Always call this tool before attempting to reserve a seat or when an attendee
    asks how many open seats remain in a specific workshop (such as 'ws-101').

    Args:
        workshop_id: The unique workshop identifier, such as 'ws-101' or 'ws-102'.

    Returns:
        A dictionary with 'status', 'workshop_id', 'seats_remaining', and 'is_full'.
    """
    conn = get_db_connection()
    normalized_id = workshop_id.strip().lower()
    row = conn.execute(
        """
        SELECT workshop_id, title, topic, room, capacity, booked_seats
        FROM workshops
        WHERE LOWER(workshop_id) = ?
        """,
        (normalized_id,),
    ).fetchone()

    if row is None:
        return {
            "status": "not_found",
            "workshop_id": normalized_id,
            "message": f"Workshop '{normalized_id}' was not found in the schedule.",
        }

    info = WorkshopInfo(
        workshop_id=row["workshop_id"],
        title=row["title"],
        topic=row["topic"],
        room=row["room"],
        capacity=row["capacity"],
        booked_seats=row["booked_seats"],
    )
    return {
        "status": "success",
        "workshop_id": info.workshop_id,
        "title": info.title,
        "room": info.room,
        "capacity": info.capacity,
        "booked_seats": info.booked_seats,
        "seats_remaining": info.seats_remaining,
        "is_full": info.seats_remaining == 0,
    }


def reserve_workshop_seat(
    workshop_id: str,
    attendee_name: str,
    attendee_email: str,
    seats_requested: int = 1,
    manager_approved: bool = False,
) -> dict[str, Any]:
    """Reserves seats in a workshop for an attendee if capacity and approval rules allow.

    Use this tool only when an attendee explicitly asks to book or reserve a seat
    and provides their name and email address. Requests for 5 or more seats require
    human manager approval (`manager_approved=True`).

    Args:
        workshop_id: The workshop identifier to book (for example, 'ws-101').
        attendee_name: Full name of the attendee reserving the seat.
        attendee_email: Email address of the attendee for confirmation.
        seats_requested: Number of seats to reserve (default 1). Group requests of 5+
                         return 'pending_human_approval' unless manager_approved=True.
        manager_approved: True only after a human organizer approves a group booking.

    Returns:
        A dictionary describing whether the reservation succeeded, is pending approval, or failed.
    """
    conn = get_db_connection()
    normalized_id = workshop_id.strip().lower()
    clean_name = attendee_name.strip()
    clean_email = attendee_email.strip().lower()

    if not clean_name or "@" not in clean_email or seats_requested < 1:
        return {
            "status": "invalid_input",
            "message": "A valid attendee name, email address, and seats_requested >= 1 are required.",
        }

    # Human-in-the-Loop Approval Gate (ambient-expense-agent / long-horizon-harness pattern):
    # High-impact actions (group bookings of 5+ seats) pause and wait for human sign-off.
    if seats_requested >= 5 and not manager_approved:
        return {
            "status": "pending_human_approval",
            "requires_approval": True,
            "workshop_id": normalized_id,
            "attendee_email": clean_email,
            "seats_requested": seats_requested,
            "message": (
                f"Group booking of {seats_requested} seats in {normalized_id} requires "
                f"human organizer approval before seats are deducted."
            ),
        }

    availability = check_seat_availability(normalized_id)
    if availability["status"] != "success":
        return availability

    if availability["is_full"] or availability["seats_remaining"] < seats_requested:
        return {
            "status": "workshop_full",
            "workshop_id": normalized_id,
            "title": availability["title"],
            "seats_remaining": availability["seats_remaining"],
            "message": f"Sorry, {availability['title']} ({normalized_id}) does not have enough open seats.",
        }

    existing = conn.execute(
        """
        SELECT reservation_id
        FROM reservations
        WHERE workshop_id = ? AND attendee_email = ?
        """,
        (normalized_id, clean_email),
    ).fetchone()
    if existing is not None:
        return {
            "status": "duplicate_booking",
            "workshop_id": normalized_id,
            "attendee_email": clean_email,
            "message": f"{clean_email} already has a confirmed seat in {normalized_id}.",
        }

    with conn:
        conn.execute(
            """
            INSERT INTO reservations (workshop_id, attendee_name, attendee_email)
            VALUES (?, ?, ?)
            """,
            (normalized_id, clean_name, clean_email),
        )
        conn.execute(
            """
            UPDATE workshops
            SET booked_seats = booked_seats + ?
            WHERE workshop_id = ?
            """,
            (seats_requested, normalized_id),
        )

    updated = check_seat_availability(normalized_id)
    return {
        "status": "confirmed",
        "workshop_id": normalized_id,
        "title": updated["title"],
        "room": updated["room"],
        "attendee_name": clean_name,
        "attendee_email": clean_email,
        "seats_booked": seats_requested,
        "seats_remaining": updated["seats_remaining"],
        "message": (
            f"Seat confirmed for {clean_name} in {updated['title']} "
            f"({normalized_id}, {updated['room']})."
        ),
    }


def screen_user_message_safety(prompt: str) -> dict[str, Any]:
    """Runner-wide safety pre-check (`safety-plugins` recipe pattern).

    Screens incoming user prompts for obvious prompt-injection or instruction-override
    attempts before the message is routed to any sub-agent or tool.
    """
    lowered = prompt.lower()
    blocked_phrases = (
        "ignore all previous instructions",
        "drop table workshops",
        "bypass approval",
        "system prompt:",
    )
    for phrase in blocked_phrases:
        if phrase in lowered:
            return {
                "allowed": False,
                "reason": f"Blocked by runner safety screen (matched pattern: '{phrase}').",
            }
    return {"allowed": True, "reason": "ok"}


# ---------------------------------------------------------------------------
# 4. Google ADK Multi-Agent Definitions
# ---------------------------------------------------------------------------

MODEL_ID = "gemini-3-flash-preview"

catalog_specialist = Agent(
    name="catalog_specialist",
    model=MODEL_ID,
    description=(
        "Handles questions about conference workshop schedules, topics, "
        "and open seat availability."
    ),
    instruction=(
        "You are the Catalog Specialist for Cloud Builders Day. "
        "Always use `search_workshops` when attendees ask about topics or schedules, "
        "and use `check_seat_availability` when they ask how many seats are left in a "
        "specific workshop ID. Never guess workshop titles or seat counts."
    ),
    tools=[search_workshops, check_seat_availability],
)

booking_specialist = Agent(
    name="booking_specialist",
    model=MODEL_ID,
    description=(
        "Handles seat reservations for conference workshops after verifying "
        "that seats are available."
    ),
    instruction=(
        "You are the Booking Specialist for Cloud Builders Day. "
        "Before reserving a seat, always call `check_seat_availability` first. "
        "If seats are available, call `reserve_workshop_seat` with the workshop_id, "
        "attendee_name, and attendee_email. If the workshop is full, politely inform "
        "the attendee without calling `reserve_workshop_seat`."
    ),
    tools=[check_seat_availability, reserve_workshop_seat],
)

root_agent = Agent(
    name="event_concierge_coordinator",
    model=MODEL_ID,
    description=(
        "Main conference concierge that routes schedule questions to the "
        "catalog_specialist and booking requests to the booking_specialist."
    ),
    instruction=(
        "You are the Welcome Desk Coordinator for Cloud Builders Day. "
        "Delegate schedule discovery and seat-count questions to `catalog_specialist`. "
        "Delegate seat booking and reservation requests to `booking_specialist`. "
        "Always base your answers strictly on tool outputs."
    ),
    sub_agents=[catalog_specialist, booking_specialist],
)


# ---------------------------------------------------------------------------
# 5. Deterministic Local Tool-Loop Runner & Trajectory Evaluator
# ---------------------------------------------------------------------------


def _extract_workshop_id(prompt: str) -> str | None:
    match = re.search(r"\b(ws-\d{3})\b", prompt, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _extract_booking_details(prompt: str) -> tuple[str, str]:
    email_match = re.search(r"([\w\.\-+]+@[\w\.\-]+\.\w+)", prompt)
    email = email_match.group(1) if email_match else "guest@example.com"

    name_match = re.search(
        r"for\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(",
        prompt,
    )
    name = name_match.group(1).strip() if name_match else "Conference Attendee"
    return name, email


def run_concierge_turn(prompt: str) -> AgentTurnTrace:
    """Execute the multi-agent tool loop deterministically for local testing & evals.

    Mirrors the exact delegation and tool-calling contract configured on `root_agent`,
    `catalog_specialist`, and `booking_specialist` so developers can verify tool
    routing and evaluation datasets offline before burning live API tokens.
    """
    lowered = prompt.lower()
    workshop_id = _extract_workshop_id(prompt)
    tool_calls: list[ToolCallRecord] = []

    is_booking_request = any(
        word in lowered for word in ("reserve", "book", "register", "sign up")
    )

    if is_booking_request and workshop_id:
        delegated_agent = booking_specialist.name
        avail_args = {"workshop_id": workshop_id}
        avail_out = check_seat_availability(**avail_args)
        tool_calls.append(
            ToolCallRecord(
                tool_name="check_seat_availability",
                arguments=avail_args,
                output=avail_out,
            )
        )

        if avail_out.get("status") != "success":
            return AgentTurnTrace(
                user_prompt=prompt,
                delegated_agent=delegated_agent,
                tool_calls=tool_calls,
                final_response=str(avail_out.get("message", "Workshop not found.")),
            )

        if avail_out.get("is_full"):
            return AgentTurnTrace(
                user_prompt=prompt,
                delegated_agent=delegated_agent,
                tool_calls=tool_calls,
                final_response=(
                    f"Sorry, {avail_out['title']} ({workshop_id}) is currently full "
                    f"(0 open seats remaining)."
                ),
            )

        attendee_name, attendee_email = _extract_booking_details(prompt)
        reserve_args = {
            "workshop_id": workshop_id,
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
        }
        reserve_out = reserve_workshop_seat(**reserve_args)
        tool_calls.append(
            ToolCallRecord(
                tool_name="reserve_workshop_seat",
                arguments=reserve_args,
                output=reserve_out,
            )
        )
        return AgentTurnTrace(
            user_prompt=prompt,
            delegated_agent=delegated_agent,
            tool_calls=tool_calls,
            final_response=str(reserve_out.get("message", "Reservation processed.")),
        )

    delegated_agent = catalog_specialist.name
    if workshop_id and any(word in lowered for word in ("seat", "open", "left", "available")):
        avail_args = {"workshop_id": workshop_id}
        avail_out = check_seat_availability(**avail_args)
        tool_calls.append(
            ToolCallRecord(
                tool_name="check_seat_availability",
                arguments=avail_args,
                output=avail_out,
            )
        )
        if avail_out.get("status") == "success":
            response_text = (
                f"Workshop {avail_out['workshop_id']} ({avail_out['title']}) has "
                f"{avail_out['seats_remaining']} open seats left in {avail_out['room']}."
            )
        else:
            response_text = str(avail_out.get("message", "Workshop not found."))
        return AgentTurnTrace(
            user_prompt=prompt,
            delegated_agent=delegated_agent,
            tool_calls=tool_calls,
            final_response=response_text,
        )

    topic = ""
    for candidate in ("python", "agents", "cloud-run", "cloud run"):
        if candidate in lowered:
            topic = candidate.replace(" ", "-")
            break

    search_args = {"topic": topic}
    search_out = search_workshops(**search_args)
    tool_calls.append(
        ToolCallRecord(
            tool_name="search_workshops",
            arguments=search_args,
            output=search_out,
        )
    )
    matches = search_out.get("workshops", [])
    if not matches:
        response_text = f"No workshops found matching topic '{topic}'."
    else:
        formatted = ", ".join(
            f"{w['workshop_id']}: {w['title']} ({w['seats_remaining']} seats open)"
            for w in matches
        )
        response_text = f"Found {len(matches)} workshop(s): {formatted}."

    return AgentTurnTrace(
        user_prompt=prompt,
        delegated_agent=delegated_agent,
        tool_calls=tool_calls,
        final_response=response_text,
    )


def evaluate_agent_trajectories(dataset_path: str | Path) -> EvalSummaryReport:
    """Run all evaluation cases in `eval_dataset.json` and grade tool trajectories.

    Checks three criteria per case:
    1. Did the coordinator route to the expected specialist sub-agent?
    2. Did the specialist call the exact expected sequence of tools?
    3. Did the final response stay grounded in the tool output keywords?
    """
    reset_workshop_store()
    path = Path(dataset_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    eval_cases = payload.get("eval_cases", [])

    results: list[EvalCaseResult] = []
    for case in eval_cases:
        case_id = case["eval_case_id"]
        parts = case["prompt"]["parts"]
        prompt_text = " ".join(part.get("text", "") for part in parts).strip()

        trace = run_concierge_turn(prompt_text)

        expected_delegate = case.get("expected_delegate", "")
        expected_trajectory = list(case.get("expected_tool_trajectory", []))
        expected_keywords = list(case.get("expected_response_keywords", []))

        delegate_matched = trace.delegated_agent == expected_delegate
        trajectory_matched = trace.tool_trajectory == expected_trajectory
        keywords_matched = all(
            kw.lower() in trace.final_response.lower() for kw in expected_keywords
        )

        results.append(
            EvalCaseResult(
                eval_case_id=case_id,
                delegate_matched=delegate_matched,
                trajectory_matched=trajectory_matched,
                keywords_matched=keywords_matched,
                actual_trajectory=trace.tool_trajectory,
                expected_trajectory=expected_trajectory,
                final_response=trace.final_response,
            )
        )

    total = len(results)
    passed = sum(1 for item in results if item.passed)
    accuracy = (passed / total) if total > 0 else 0.0
    return EvalSummaryReport(
        total_cases=total,
        passed_cases=passed,
        trajectory_accuracy=accuracy,
        results=results,
    )


if __name__ == "__main__":
    default_dataset = Path(__file__).with_name("eval_dataset.json")
    report = evaluate_agent_trajectories(default_dataset)
    print(
        f"Evaluated {report.total_cases} cases | "
        f"Passed: {report.passed_cases}/{report.total_cases} "
        f"({report.trajectory_accuracy * 100:.1f}%)"
    )
    for item in report.results:
        status = "PASS" if item.passed else "FAIL"
        print(f"  [{status}] {item.eval_case_id}: tools={item.actual_trajectory}")

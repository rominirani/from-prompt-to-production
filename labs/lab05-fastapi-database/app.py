"""Lab 05: Workshop & Event Registration API with FastAPI and SQLite.

Demonstrates FastAPI routes, dependency injection, Pydantic v2 validation,
parameterized SQL queries, atomic capacity enforcement, and security headers.
"""

from __future__ import annotations

from collections.abc import Generator
import os
import re
import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# 1. Pydantic v2 Request & Response Models
# ---------------------------------------------------------------------------


class WorkshopCreate(BaseModel):
    """Payload for creating a new workshop event."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    title: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description="Title of the workshop (e.g., 'Building Agents with ADK').",
    )
    instructor: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Name of the workshop instructor.",
    )
    capacity: int = Field(
        ...,
        ge=1,
        le=500,
        description="Maximum number of seats available (1 to 500).",
    )


class WorkshopResponse(BaseModel):
    """Workshop details returned by the API."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    instructor: str
    capacity: int
    registered_count: int
    seats_remaining: int


class RegistrationCreate(BaseModel):
    """Payload for registering an attendee for a workshop."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    attendee_name: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Full name of the attendee.",
    )
    attendee_email: str = Field(
        ...,
        min_length=5,
        max_length=120,
        description="Email address of the attendee.",
    )

    @field_validator("attendee_email")
    @classmethod
    def validate_and_normalize_email(cls, value: str) -> str:
        """Normalize email to lowercase and verify basic email structure."""
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise ValueError("Invalid email address format.")
        return normalized


class RegistrationResponse(BaseModel):
    """Confirmation returned when an attendee registers for a workshop."""

    model_config = ConfigDict(frozen=True)

    id: int
    workshop_id: int
    attendee_name: str
    attendee_email: str


# ---------------------------------------------------------------------------
# 2. Database Connection & Schema Initialization
# ---------------------------------------------------------------------------


def get_database_path() -> str:
    """Return the configured SQLite database file path."""
    return os.environ.get("WORKSHOP_DB_PATH", "workshops.db")


def init_db(db_path: str | None = None) -> None:
    """Create the workshops and registrations tables if they do not exist."""
    target_path = db_path or get_database_path()
    with sqlite3.connect(target_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workshops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                instructor TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK (capacity >= 1),
                registered_count INTEGER NOT NULL DEFAULT 0
                    CHECK (registered_count >= 0 AND registered_count <= capacity)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id INTEGER NOT NULL,
                attendee_name TEXT NOT NULL,
                attendee_email TEXT NOT NULL,
                FOREIGN KEY (workshop_id) REFERENCES workshops(id) ON DELETE CASCADE,
                UNIQUE (workshop_id, attendee_email)
            );
            """
        )


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that yields a SQLite connection with Row factory enabled."""
    db_path = get_database_path()
    init_db(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


DbConnection = Annotated[sqlite3.Connection, Depends(get_db)]


# ---------------------------------------------------------------------------
# 3. FastAPI Application, Security Headers Middleware & Routes
# ---------------------------------------------------------------------------

# TODO(security): Attach OAuth2/JWT authentication and per-IP rate limiting
# middleware (covered in Chapter 8) before exposing write endpoints publicly.
app = FastAPI(
    title="Workshop & Event Registration API",
    description="Lab 05: Production-style FastAPI + SQLite backend with atomic seat limits.",
    version="1.0.0",
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    """Attach standard security headers to every HTTP response."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


def _row_to_workshop(row: sqlite3.Row) -> WorkshopResponse:
    """Convert a sqlite3.Row into a WorkshopResponse model."""
    capacity = int(row["capacity"])
    registered = int(row["registered_count"])
    return WorkshopResponse(
        id=int(row["id"]),
        title=str(row["title"]),
        instructor=str(row["instructor"]),
        capacity=capacity,
        registered_count=registered,
        seats_remaining=capacity - registered,
    )


@app.post(
    "/workshops",
    response_model=WorkshopResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workshop(payload: WorkshopCreate, conn: DbConnection) -> WorkshopResponse:
    """Create a new workshop with a fixed seat capacity."""
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO workshops (title, instructor, capacity, registered_count)
            VALUES (?, ?, ?, 0)
            """,
            (payload.title, payload.instructor, payload.capacity),
        )
        workshop_id = cursor.lastrowid

    row = conn.execute(
        "SELECT id, title, instructor, capacity, registered_count FROM workshops WHERE id = ?",
        (workshop_id,),
    ).fetchone()
    return _row_to_workshop(row)


@app.get("/workshops", response_model=list[WorkshopResponse])
def list_workshops(
    conn: DbConnection,
    search: str | None = None,
) -> list[WorkshopResponse]:
    """List all workshops, optionally filtered safely by title keyword."""
    if search:
        pattern = f"%{search.strip()}%"
        rows = conn.execute(
            """
            SELECT id, title, instructor, capacity, registered_count
            FROM workshops
            WHERE title LIKE ?
            ORDER BY id ASC
            """,
            (pattern,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, title, instructor, capacity, registered_count
            FROM workshops
            ORDER BY id ASC
            """
        ).fetchall()
    return [_row_to_workshop(row) for row in rows]


@app.get("/workshops/{workshop_id}", response_model=WorkshopResponse)
def get_workshop(workshop_id: int, conn: DbConnection) -> WorkshopResponse:
    """Fetch a single workshop by ID or return 404 Not Found."""
    row = conn.execute(
        "SELECT id, title, instructor, capacity, registered_count FROM workshops WHERE id = ?",
        (workshop_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workshop {workshop_id} not found.",
        )
    return _row_to_workshop(row)


@app.post(
    "/workshops/{workshop_id}/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_attendee(
    workshop_id: int,
    payload: RegistrationCreate,
    conn: DbConnection,
) -> RegistrationResponse:
    """Register an attendee atomically, preventing duplicate emails or overbooking."""
    workshop_row = conn.execute(
        "SELECT id, capacity, registered_count FROM workshops WHERE id = ?",
        (workshop_id,),
    ).fetchone()
    if workshop_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workshop {workshop_id} not found.",
        )

    existing = conn.execute(
        """
        SELECT id FROM registrations
        WHERE workshop_id = ? AND attendee_email = ?
        """,
        (workshop_id, payload.attendee_email),
    ).fetchone()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered for this workshop.",
        )

    try:
        with conn:
            update_cursor = conn.execute(
                """
                UPDATE workshops
                SET registered_count = registered_count + 1
                WHERE id = ? AND registered_count < capacity
                """,
                (workshop_id,),
            )
            if update_cursor.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Workshop is already at full capacity.",
                )

            insert_cursor = conn.execute(
                """
                INSERT INTO registrations (workshop_id, attendee_name, attendee_email)
                VALUES (?, ?, ?)
                """,
                (workshop_id, payload.attendee_name, payload.attendee_email),
            )
            registration_id = int(insert_cursor.lastrowid or 0)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration conflict: duplicate email or capacity limit reached.",
        ) from exc

    return RegistrationResponse(
        id=registration_id,
        workshop_id=workshop_id,
        attendee_name=payload.attendee_name,
        attendee_email=payload.attendee_email,
    )


@app.get(
    "/workshops/{workshop_id}/registrations",
    response_model=list[RegistrationResponse],
)
def list_registrations(
    workshop_id: int,
    conn: DbConnection,
) -> list[RegistrationResponse]:
    """Return all confirmed registrations for a specific workshop."""
    workshop_row = conn.execute(
        "SELECT id FROM workshops WHERE id = ?",
        (workshop_id,),
    ).fetchone()
    if workshop_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workshop {workshop_id} not found.",
        )

    rows = conn.execute(
        """
        SELECT id, workshop_id, attendee_name, attendee_email
        FROM registrations
        WHERE workshop_id = ?
        ORDER BY id ASC
        """,
        (workshop_id,),
    ).fetchall()
    return [
        RegistrationResponse(
            id=int(r["id"]),
            workshop_id=int(r["workshop_id"]),
            attendee_name=str(r["attendee_name"]),
            attendee_email=str(r["attendee_email"]),
        )
        for r in rows
    ]


if __name__ == "__main__":
    import uvicorn

    init_db()
    # Always bind to 127.0.0.1 during local development and testing
    uvicorn.run(app, host="127.0.0.1", port=8000)

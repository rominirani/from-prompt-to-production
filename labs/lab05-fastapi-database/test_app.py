"""Automated API tests for Lab 05: Workshop & Event Registration API."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from fastapi.testclient import TestClient

# Ensure the lab directory is importable regardless of current working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import app, init_db


def _create_isolated_client() -> tuple[TestClient, str]:
    """Create a TestClient backed by a fresh temporary SQLite database file."""
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["WORKSHOP_DB_PATH"] = temp_db_path
    init_db(temp_db_path)
    return TestClient(app), temp_db_path


def _cleanup_db(temp_db_path: str) -> None:
    """Remove temporary SQLite database file after test completion."""
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


def test_create_and_fetch_workshop_with_security_headers() -> None:
    """Creating a workshop returns 201 Created, seat counts, and security headers."""
    client, db_path = _create_isolated_client()
    try:
        response = client.post(
            "/workshops",
            json={
                "title": "  Building Reliable Agents with ADK  ",
                "instructor": "Romin Irani",
                "capacity": 2,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Building Reliable Agents with ADK"
        assert data["instructor"] == "Romin Irani"
        assert data["capacity"] == 2
        assert data["registered_count"] == 0
        assert data["seats_remaining"] == 2

        # Verify mandatory HTTP security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "default-src 'self'" in response.headers.get(
            "Content-Security-Policy", ""
        )

        # Fetch by ID
        get_resp = client.get("/workshops/1")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Building Reliable Agents with ADK"
    finally:
        _cleanup_db(db_path)


def test_register_attendees_and_block_overbooking_with_409() -> None:
    """Registering up to capacity succeeds; the next registration returns 409 Conflict."""
    client, db_path = _create_isolated_client()
    try:
        ws_resp = client.post(
            "/workshops",
            json={
                "title": "FastAPI & Cloud SQL Hands-On",
                "instructor": "Maya Lin",
                "capacity": 2,
            },
        )
        workshop_id = ws_resp.json()["id"]

        # Seat 1 of 2
        reg1 = client.post(
            f"/workshops/{workshop_id}/register",
            json={"attendee_name": "Liam Chen", "attendee_email": "Liam@Example.com"},
        )
        assert reg1.status_code == 201
        assert reg1.json()["attendee_email"] == "liam@example.com"

        # Seat 2 of 2
        reg2 = client.post(
            f"/workshops/{workshop_id}/register",
            json={"attendee_name": "Noah Patel", "attendee_email": "noah@example.com"},
        )
        assert reg2.status_code == 201

        # Verify seats_remaining is now 0
        ws_after = client.get(f"/workshops/{workshop_id}").json()
        assert ws_after["registered_count"] == 2
        assert ws_after["seats_remaining"] == 0

        # Seat 3 of 2 -> Must fail with 409 Conflict!
        reg3 = client.post(
            f"/workshops/{workshop_id}/register",
            json={"attendee_name": "Sofia Gomez", "attendee_email": "sofia@example.com"},
        )
        assert reg3.status_code == 409
        assert "full capacity" in reg3.json()["detail"].lower()

        # Confirm registered_count stayed at 2 and only 2 attendees are listed
        registrations = client.get(f"/workshops/{workshop_id}/registrations").json()
        assert len(registrations) == 2
    finally:
        _cleanup_db(db_path)


def test_duplicate_email_registration_returns_409_conflict() -> None:
    """Registering the same email twice for the same workshop returns 409 Conflict."""
    client, db_path = _create_isolated_client()
    try:
        ws_resp = client.post(
            "/workshops",
            json={"title": "Pydantic v2 Deep Dive", "instructor": "Alex Rivera", "capacity": 5},
        )
        workshop_id = ws_resp.json()["id"]

        first = client.post(
            f"/workshops/{workshop_id}/register",
            json={"attendee_name": "Priya Nair", "attendee_email": "priya@example.com"},
        )
        assert first.status_code == 201

        # Same email with different casing and spaces
        duplicate = client.post(
            f"/workshops/{workshop_id}/register",
            json={"attendee_name": "Priya Nair", "attendee_email": "  PRIYA@example.com "},
        )
        assert duplicate.status_code == 409
        assert "already registered" in duplicate.json()["detail"].lower()

        # Confirm seat was NOT consumed by the failed duplicate attempt
        ws_state = client.get(f"/workshops/{workshop_id}").json()
        assert ws_state["registered_count"] == 1
        assert ws_state["seats_remaining"] == 4
    finally:
        _cleanup_db(db_path)


def test_invalid_email_or_capacity_returns_422_unprocessable_entity() -> None:
    """Invalid payloads are stopped at the Pydantic boundary with 422."""
    client, db_path = _create_isolated_client()
    try:
        bad_workshop = client.post(
            "/workshops",
            json={"title": "Valid Title", "instructor": "Valid Name", "capacity": 0},
        )
        assert bad_workshop.status_code == 422

        ws_resp = client.post(
            "/workshops",
            json={"title": "Valid Workshop", "instructor": "Valid Name", "capacity": 10},
        )
        workshop_id = ws_resp.json()["id"]

        bad_email = client.post(
            f"/workshops/{workshop_id}/register",
            json={"attendee_name": "Samir", "attendee_email": "not-an-email-address"},
        )
        assert bad_email.status_code == 422
    finally:
        _cleanup_db(db_path)


def test_missing_workshop_returns_404_not_found() -> None:
    """Fetching or registering for a non-existent workshop ID returns 404."""
    client, db_path = _create_isolated_client()
    try:
        assert client.get("/workshops/999").status_code == 404
        assert (
            client.post(
                "/workshops/999/register",
                json={"attendee_name": "Maya", "attendee_email": "maya@example.com"},
            ).status_code
            == 404
        )
    finally:
        _cleanup_db(db_path)


def test_sql_injection_payloads_are_neutralized_by_parameterized_queries() -> None:
    """SQL injection strings in search or registration fields are treated as harmless text."""
    client, db_path = _create_isolated_client()
    try:
        client.post(
            "/workshops",
            json={
                "title": "Cloud SQL & AlloyDB Fundamentals",
                "instructor": "Romin Irani",
                "capacity": 10,
            },
        )

        # Attempt classic SQL injection in query string search
        sqli_search = "' OR '1'='1'; DROP TABLE workshops; --"
        search_resp = client.get("/workshops", params={"search": sqli_search})
        assert search_resp.status_code == 200
        assert search_resp.json() == []

        # Attempt SQL injection inside attendee_name
        reg_resp = client.post(
            "/workshops/1/register",
            json={
                "attendee_name": "Robert'); DROP TABLE workshops;--",
                "attendee_email": "bobby.tables@example.com",
            },
        )
        assert reg_resp.status_code == 201

        # Verify the workshops table is completely intact and stores the literal string safely
        all_workshops = client.get("/workshops").json()
        assert len(all_workshops) == 1
        assert all_workshops[0]["registered_count"] == 1
    finally:
        _cleanup_db(db_path)


if __name__ == "__main__":
    test_functions = [
        test_create_and_fetch_workshop_with_security_headers,
        test_register_attendees_and_block_overbooking_with_409,
        test_duplicate_email_registration_returns_409_conflict,
        test_invalid_email_or_capacity_returns_422_unprocessable_entity,
        test_missing_workshop_returns_404_not_found,
        test_sql_injection_payloads_are_neutralized_by_parameterized_queries,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 05 API tests passed!")

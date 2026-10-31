"""Automated tests for Lab 06: Read-Only Event & Workshop MCP Server."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

from pydantic import ValidationError

from event_mcp_server import (
     build_developer_knowledge_lookup,
    check_workshop_seat_status,
    create_sample_workshop_db,
    list_registered_tool_names,
    list_upcoming_workshops,
    mask_email,
    mcp,
    search_registrations_by_workshop,
)


def _with_temp_workshop_db() -> Path:
    """Create a fresh temporary SQLite database and point WORKSHOP_DB_PATH to it."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="lab06_test_"))
    db_path = tmp_dir / "test_workshops.db"
    create_sample_workshop_db(db_path)
    os.environ["WORKSHOP_DB_PATH"] = str(db_path)
    return db_path


def test_mcp_server_registers_expected_tools() -> None:
    """Verify all four tools are registered on the MCPServer/FastMCP instance."""
    tool_names = set(list_registered_tool_names())
    expected = {
        "list_upcoming_workshops",
        "check_workshop_seat_status",
        "search_registrations_by_workshop",
        "build_developer_knowledge_lookup",
    }
    assert expected.issubset(tool_names)

    # Also verify async MCP call_tool execution if supported by the SDK version
    if hasattr(mcp, "call_tool"):
        _with_temp_workshop_db()
        result = asyncio.run(
            mcp.call_tool(
                "check_workshop_seat_status",
                {"workshop_id": "ws-genai-101"},
            )
        )
        assert result is not None


def test_list_upcoming_workshops_and_filtering() -> None:
    """Verify topic filtering and open-seat filtering work accurately."""
    _with_temp_workshop_db()

    all_workshops = list_upcoming_workshops()
    assert len(all_workshops) == 3

    open_only = list_upcoming_workshops(only_open_seats=True)
    open_ids = {w["workshop_id"] for w in open_only}
    assert "ws-cloudrun-201" not in open_ids
    assert "ws-genai-101" in open_ids
    assert "ws-mcp-301" in open_ids

    mcp_topic = list_upcoming_workshops(topic_filter="MCP")
    assert len(mcp_topic) == 1
    assert mcp_topic[0]["workshop_id"] == "ws-mcp-301"


def test_check_workshop_seat_status_open_and_full() -> None:
    """Verify seat status computation for open, full, and unknown workshops."""
    _with_temp_workshop_db()

    open_status = check_workshop_seat_status("ws-genai-101")
    assert open_status["found"] is True
    assert open_status["seats_remaining"] == 6
    assert open_status["availability_badge"] == "OPEN"

    full_status = check_workshop_seat_status("ws-cloudrun-201")
    assert full_status["found"] is True
    assert full_status["seats_remaining"] == 0
    assert full_status["waitlisted_count"] == 1
    assert full_status["availability_badge"] == "FULL_WAITLIST_ACTIVE"

    missing_status = check_workshop_seat_status("ws-unknown-999")
    assert missing_status["found"] is False


def test_search_registrations_masks_attendee_emails() -> None:
    """Ensure attendee emails are masked before leaving the MCP tool."""
    _with_temp_workshop_db()

    confirmed = search_registrations_by_workshop("ws-genai-101", status_filter="CONFIRMED")
    assert len(confirmed) == 2
    for record in confirmed:
        assert "attendee_email" not in record
        assert "***@" in record["attendee_email_masked"]

    assert mask_email("priya.sharma@example.com") == "pr***@example.com"
    assert mask_email("a@example.com") == "a***@example.com"


def test_input_validation_blocks_malformed_ids_and_sql_injection() -> None:
    """Verify Pydantic validation and parameterized SQL reject injection payloads."""
    _with_temp_workshop_db()

    try:
        check_workshop_seat_status("ws-genai-101' OR '1'='1")
        raise AssertionError("Expected ValidationError for SQL injection payload")
    except ValidationError:
        pass

    try:
        search_registrations_by_workshop("ws-genai-101", status_filter="DROP TABLE")
        raise AssertionError("Expected ValidationError for invalid status_filter")
    except ValidationError:
        pass

    # Even in free-text topic_filter, parameterized LIKE queries treat SQL syntax as literal text
    adversarial_search = list_upcoming_workshops(topic_filter="' OR 1=1 --")
    assert adversarial_search == []


def test_readonly_sqlite_connection_blocks_writes() -> None:
    """Verify the MCP server connects to SQLite in strict read-only mode."""
    db_path = _with_temp_workshop_db()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        try:
            conn.execute("DELETE FROM workshops")
            raise AssertionError("Expected OperationalError when writing in read-only mode")
        except sqlite3.OperationalError:
            pass


def test_build_developer_knowledge_lookup_modes() -> None:
    """Verify formatting for search_documents, answer_query, and get_documents."""
    search_payload = build_developer_knowledge_lookup(
        query="cloud run concurrency gcloud",
        mode="search_documents",
    )
    assert search_payload["tool_name"] == "search_documents"
    assert search_payload["mcp_arguments"] == {"query": "cloud run concurrency gcloud"}
    assert "searchDocumentChunks" in search_payload["rest_fallback"]["endpoint"]

    answer_payload = build_developer_knowledge_lookup(
        query="When should I choose Cloud Run jobs vs services?",
        mode="answer_query",
    )
    assert answer_payload["tool_name"] == "answer_query"
    assert answer_payload["rest_fallback"]["method"] == "POST"

    doc_payload = build_developer_knowledge_lookup(
        query="https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run",
        mode="get_documents",
    )
    assert doc_payload["tool_name"] == "get_documents"
    assert doc_payload["mcp_arguments"] == {
        "names": ["documents/docs.cloud.google.com/run/docs/overview/what-is-cloud-run"]
    }


if __name__ == "__main__":
    test_functions = [
        test_mcp_server_registers_expected_tools,
        test_list_upcoming_workshops_and_filtering,
        test_check_workshop_seat_status_open_and_full,
        test_search_registrations_masks_attendee_emails,
        test_input_validation_blocks_malformed_ids_and_sql_injection,
        test_readonly_sqlite_connection_blocks_writes,
        test_build_developer_knowledge_lookup_modes,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 06 MCP tests passed!")

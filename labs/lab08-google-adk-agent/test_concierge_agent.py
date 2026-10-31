"""Automated tests for Lab 08: Multi-Agent Event Concierge with Google ADK."""

from __future__ import annotations

from pathlib import Path

from concierge_agent import (
     booking_specialist,
    catalog_specialist,
    check_seat_availability,
    evaluate_agent_trajectories,
    reserve_workshop_seat,
    reset_workshop_store,
    root_agent,
    run_concierge_turn,
    search_workshops,
)


def test_adk_agent_hierarchy_and_tools() -> None:
    """Verify the Google ADK root agent and specialist sub-agents are wired properly."""
    assert root_agent.name == "event_concierge_coordinator"
    sub_agent_names = [agent.name for agent in root_agent.sub_agents]
    assert sub_agent_names == ["catalog_specialist", "booking_specialist"]

    catalog_tool_names = [fn.__name__ for fn in catalog_specialist.tools]
    assert "search_workshops" in catalog_tool_names
    assert "check_seat_availability" in catalog_tool_names

    booking_tool_names = [fn.__name__ for fn in booking_specialist.tools]
    assert "check_seat_availability" in booking_tool_names
    assert "reserve_workshop_seat" in booking_tool_names


def test_search_and_availability_tools() -> None:
    """Verify workshop search and seat availability queries return accurate data."""
    reset_workshop_store()

    python_results = search_workshops("python")
    assert python_results["status"] == "success"
    assert python_results["count"] == 1
    assert python_results["workshops"][0]["workshop_id"] == "ws-101"

    avail_101 = check_seat_availability("ws-101")
    assert avail_101["status"] == "success"
    assert avail_101["seats_remaining"] == 2
    assert avail_101["is_full"] is False

    avail_102 = check_seat_availability("ws-102")
    assert avail_102["status"] == "success"
    assert avail_102["seats_remaining"] == 0
    assert avail_102["is_full"] is True


def test_reservation_and_capacity_guardrails() -> None:
    """Verify seat reservations decrement capacity, block duplicates, and reject full workshops."""
    reset_workshop_store()

    # 1. Valid booking on ws-101
    booking = reserve_workshop_seat("ws-101", "Priya Nair", "priya@example.com")
    assert booking["status"] == "confirmed"
    assert booking["seats_remaining"] == 1

    # 2. Duplicate booking for same email on ws-101 is prevented
    duplicate = reserve_workshop_seat("ws-101", "Priya Nair", "priya@example.com")
    assert duplicate["status"] == "duplicate_booking"

    # 3. Booking a full workshop (ws-102) is rejected cleanly
    full_attempt = reserve_workshop_seat("ws-102", "Alex Rivera", "alex@example.com")
    assert full_attempt["status"] == "workshop_full"
    assert full_attempt["seats_remaining"] == 0


def test_sql_injection_safety_in_search() -> None:
    """Ensure parameterized SQL queries treat SQL metacharacters as literal strings."""
    reset_workshop_store()
    malicious_input = "python' OR '1'='1"
    result = search_workshops(malicious_input)
    assert result["status"] == "success"
    assert result["count"] == 0


def test_trajectory_evaluation_dataset_passes_100_percent() -> None:
    """Verify the agent achieves 100% trajectory and response accuracy on eval_dataset.json."""
    dataset_path = Path(__file__).with_name("eval_dataset.json")
    report = evaluate_agent_trajectories(dataset_path)

    assert report.total_cases == 4
    assert report.passed_cases == 4
    assert report.trajectory_accuracy == 1.0

    # Verify the full workshop case stopped after check_seat_availability
    full_case = next(r for r in report.results if r.eval_case_id == "reserve_seat_full_workshop")
    assert full_case.actual_trajectory == ["check_seat_availability"]


def test_single_turn_runner_delegation() -> None:
    """Verify `run_concierge_turn` records the delegated specialist and tool calls."""
    reset_workshop_store()
    trace = run_concierge_turn(
        "Please reserve a seat in ws-103 for Sam Patel (sam@example.com)."
    )
    assert trace.delegated_agent == "booking_specialist"
    assert trace.tool_trajectory == ["check_seat_availability", "reserve_workshop_seat"]
    assert "confirmed" in trace.final_response.lower()


if __name__ == "__main__":
    test_functions = [
        test_adk_agent_hierarchy_and_tools,
        test_search_and_availability_tools,
        test_reservation_and_capacity_guardrails,
        test_sql_injection_safety_in_search,
        test_trajectory_evaluation_dataset_passes_100_percent,
        test_single_turn_runner_delegation,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 08 tests passed!")

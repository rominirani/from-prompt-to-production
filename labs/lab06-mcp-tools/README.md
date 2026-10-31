# Lab 06: Connecting Antigravity to Live Docs and Tools with MCP

In this lab, you build and test a read-only **Model Context Protocol (MCP)** server in Python that lets Google Antigravity inspect a local SQLite database of developer workshops and format live queries for the **Google Developer Knowledge** MCP server.

## What's Inside

- `event_mcp_server.py` — A runnable MCP server built with the official Python `mcp` SDK (`MCPServer` / `FastMCP`) and `Pydantic` v2 validation. It exposes four tools:
  1. `list_upcoming_workshops`: Lists scheduled developer workshops with optional topic and seat availability filters.
  2. `check_workshop_seat_status`: Computes remaining capacity and waitlist pressure for a specific workshop ID.
  3. `search_registrations_by_workshop`: Returns attendee registrations for a workshop with masked email addresses (`pr***@example.com`) so raw PII never leaks into the model context.
  4. `build_developer_knowledge_lookup`: Formats a grounded query for the official Google Developer Knowledge MCP tools (`search_documents`, `answer_query`, `get_documents`) and provides the matching REST API fallback endpoint.
- `mcp_config.example.json` — Example Antigravity MCP configuration showing both local `Stdio` (`command` + `args`) and remote `Streamable HTTP` (`url`) servers.
- `test_event_mcp_server.py` — Automated test suite verifying tool registration, parameterized SQL safety, PII masking, and input validation.

## Running the Tests

From the repository root:

```bash
uv run python labs/lab06-mcp-tools/test_event_mcp_server.py
```

Or with `pytest`:

```bash
uv run pytest labs/lab06-mcp-tools/test_event_mcp_server.py
```

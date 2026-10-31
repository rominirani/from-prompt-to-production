"""Chapter 9 Companion Demo: Security, Optimization & Scaling (Before vs. After).

Designed for AI builders who want to SEE in plain, 10-line Python examples why
a naive AI-generated snippet breaks—and how a tiny change fixes it:

1. SECURITY:     Why `f"SELECT ..."` is dangerous vs. `?` parameterized queries.
2. OPTIMIZATION: Why uncached calls waste time & Gemini tokens vs. a 5-line cache.
3. SCALING:      Why 1 runaway bot starves your server vs. a simple per-user limit.

Run from the repo root:
    uv run python labs/lab09-cloud-run-deploy/before_and_after_demo.py
"""

from __future__ import annotations

import sqlite3
import time


# ===========================================================================
# 1. SECURITY: Stopping SQL Injection with a 1-Character Change (`?`)
# ===========================================================================

def setup_sample_user_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (username TEXT, private_note TEXT)")
    conn.executemany(
        "INSERT INTO users VALUES (?, ?)",
        [
            ("alice", "Alice's secret API budget: $500"),
            ("bob", "Bob's private phone: 555-0199"),
            ("admin", "Admin backup code: 9941-8821"),
        ],
    )
    return conn


def preview_unsafe_fstring_sql(username_input: str) -> str:
    """Show the broken SQL text that an f-string produces when given `' OR '1'='1`.

    Notice how the attacker's single quote closes `username = 'alice'` early and
    injects `OR '1'='1'`, which is ALWAYS true for every row in the table!
    """
    return f"SELECT username, private_note FROM users WHERE username = '{username_input}'"


def search_user_safe(conn: sqlite3.Connection, username_input: str) -> list[tuple[str, str]]:
    """✅ AFTER (Safe): Uses a `?` placeholder so SQLite treats input strictly as data."""
    return conn.execute(
        "SELECT username, private_note FROM users WHERE username = ?",
        (username_input,),
    ).fetchall()


# ===========================================================================
# 2. OPTIMIZATION: Cutting Latency & Gemini Token Bills with a 5-Line Cache
# ===========================================================================

def run_optimization_comparison(num_visitors: int = 50) -> dict[str, float | int]:
    """Compare 50 visitors requesting the same workshop summary with vs. without a cache."""
    def slow_ai_summary_lookup(workshop_id: str) -> str:
        time.sleep(0.005)
        return f"Summary for {workshop_id}: Build reliable Python apps with Gemini 3."

    # ❌ BEFORE: Every visitor triggers a brand-new lookup (50 calls for the same data!)
    start_uncached = time.perf_counter()
    uncached_api_calls = 0
    for _ in range(num_visitors):
        uncached_api_calls += 1
        _ = slow_ai_summary_lookup("ws-101")
    uncached_ms = (time.perf_counter() - start_uncached) * 1000.0

    # ✅ AFTER: A 5-line Python dictionary cache remembers the answer for 30 seconds
    cache: dict[str, tuple[float, str]] = {}
    start_cached = time.perf_counter()
    cached_api_calls = 0

    for _ in range(num_visitors):
        now = time.monotonic()
        if "ws-101" in cache and now < cache["ws-101"][0]:
            _ = cache["ws-101"][1]
        else:
            cached_api_calls += 1
            result = slow_ai_summary_lookup("ws-101")
            cache["ws-101"] = (now + 30.0, result)

    cached_ms = (time.perf_counter() - start_cached) * 1000.0

    return {
        "visitors": num_visitors,
        "uncached_api_calls": uncached_api_calls,
        "cached_api_calls": cached_api_calls,
        "uncached_ms": round(uncached_ms, 2),
        "cached_ms": round(cached_ms, 2),
        "speedup_factor": round(uncached_ms / max(cached_ms, 0.01), 1),
    }


# ===========================================================================
# 3. SCALING: Protecting 99 Normal Users from 1 Runaway Bot
# ===========================================================================

def run_scaling_fairness_demo() -> dict[str, int]:
    """Show how a simple per-user request limit prevents 1 noisy bot from hogging capacity."""
    incoming_traffic = (
        ["runaway_bot"] * 20
        + ["normal_user_maya", "normal_user_liam", "normal_user_noah"]
    )

    max_requests_per_user = 5
    counts_by_user: dict[str, int] = {}
    accepted_bot = 0
    rejected_bot_429 = 0
    accepted_normal_users = 0

    for caller in incoming_traffic:
        current = counts_by_user.get(caller, 0)
        if current >= max_requests_per_user:
            if caller == "runaway_bot":
                rejected_bot_429 += 1
            continue

        counts_by_user[caller] = current + 1
        if caller == "runaway_bot":
            accepted_bot += 1
        else:
            accepted_normal_users += 1

    return {
        "bot_accepted": accepted_bot,
        "bot_blocked_with_429": rejected_bot_429,
        "normal_users_served_200_ok": accepted_normal_users,
    }


if __name__ == "__main__":
    print("=== 1. SECURITY DEMO: SQL Injection (Before vs. After) ===")
    db = setup_sample_user_db()
    attacker_input = "alice' OR '1'='1"
    broken_sql_preview = preview_unsafe_fstring_sql(attacker_input)
    safe_rows = search_user_safe(db, attacker_input)
    print(f"  Attacker typed: {attacker_input!r}")
    print(f"  ❌ Before (f-string SQL builds): {broken_sql_preview}")
    print("     -> Because '1'='1' is always true, running that string leaks EVERY row in the table!")
    print(f"  ✅ After  (? placeholder):       Returned {len(safe_rows)} rows -> {safe_rows}\n")

    print("=== 2. OPTIMIZATION DEMO: 50 Visitors Asking for the Same Summary ===")
    opt = run_optimization_comparison(num_visitors=50)
    print(
        f"  ❌ Before (No cache):   {opt['uncached_api_calls']} Gemini/DB calls, took {opt['uncached_ms']} ms"
    )
    print(
        f"  ✅ After  (30s cache):  {opt['cached_api_calls']} Gemini/DB call,  took {opt['cached_ms']} ms "
        f"({opt['speedup_factor']}x faster, 98% fewer API calls!)\n"
    )

    print("=== 3. SCALING DEMO: 1 Runaway Bot (20 clicks) + 3 Normal Users ===")
    scale = run_scaling_fairness_demo()
    print(
        f"  ✅ With 5-req/user cap: Bot allowed {scale['bot_accepted']}x, "
        f"blocked {scale['bot_blocked_with_429']}x (HTTP 429), "
        f"and {scale['normal_users_served_200_ok']}/3 normal users served immediately!"
    )

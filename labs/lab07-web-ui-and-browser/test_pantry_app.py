"""Automated end-to-end tests for Lab 07: Smart Pantry & Recipe Tracker Web App."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from pantry_app import app, init_pantry_db


def _setup_isolated_db() -> Path:
    """Configure an isolated temporary SQLite database for each test run."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="lab07_test_"))
    db_path = tmp_dir / "test_pantry.db"
    os.environ["PANTRY_DB_PATH"] = str(db_path)
    init_pantry_db(db_path, seed_defaults=True)
    return db_path


def test_dashboard_renders_seeded_pantry_and_htmx_attributes() -> None:
    """Verify GET / returns the full dashboard with HTMX attributes and seeded items."""
    _setup_isolated_db()
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    body = response.text

    assert "Smart Pantry &amp; Recipe Tracker" in body
    assert 'hx-post="/pantry/items"' in body
    assert 'hx-target="#pantry-table-body"' in body
    assert 'hx-post="/pantry/recipes/suggest"' in body
    assert "Chickpeas" in body
    assert "Baby Spinach" in body
    assert "LOW STOCK" in body


def test_security_headers_enforced_on_all_responses() -> None:
    """Verify strict CSP, X-Frame-Options, and X-Content-Type-Options headers."""
    _setup_isolated_db()
    client = TestClient(app)

    response = client.get("/")
    headers = response.headers

    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "camera=()" in headers["Permissions-Policy"]


def test_add_pantry_item_htmx_fragment_and_low_stock_flag() -> None:
    """Verify POST /pantry/items inserts a row and computes the low-stock badge."""
    _setup_isolated_db()
    client = TestClient(app)

    # Add an item that is low stock (quantity 0.5 <= reorder_threshold 1.0)
    res_low = client.post(
        "/pantry/items",
        json={
            "name": "Turmeric Powder",
            "category": "Spices",
            "quantity": 0.5,
            "unit": "tbsp",
            "reorder_threshold": 1.0,
        },
    )
    assert res_low.status_code == 201
    assert "Turmeric Powder" in res_low.text
    assert "LOW STOCK" in res_low.text

    # Add an item with plenty of stock (quantity 5.0 > reorder_threshold 1.0)
    res_ok = client.post(
        "/pantry/items",
        json={
            "name": "Whole Oats",
            "category": "Grains",
            "quantity": 5.0,
            "unit": "cups",
            "reorder_threshold": 1.0,
        },
    )
    assert res_ok.status_code == 201
    assert "Whole Oats" in res_ok.text
    assert "IN STOCK" in res_ok.text


def test_xss_payload_is_strictly_escaped_in_fragment_and_dashboard() -> None:
    """Ensure malicious HTML/JS in an ingredient name is escaped as harmless text."""
    _setup_isolated_db()
    client = TestClient(app)

    xss_payload = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    response = client.post(
        "/pantry/items",
        json={
            "name": xss_payload,
            "category": "Produce",
            "quantity": 3.0,
            "unit": "pcs",
            "reorder_threshold": 1.0,
        },
    )
    assert response.status_code == 201

    # Raw <script> tag must NEVER appear in the rendered fragment
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text

    # Verify it is also escaped when reading back from SQLite on GET /
    dashboard = client.get("/")
    assert "<script>alert(1)</script>" not in dashboard.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in dashboard.text


def test_invalid_category_or_negative_quantity_rejected() -> None:
    """Verify Pydantic validation blocks invalid categories and negative quantities."""
    _setup_isolated_db()
    client = TestClient(app)

    bad_response = client.post(
        "/pantry/items",
        json={
            "name": "Mystery Item",
            "category": "Explosives",
            "quantity": -5.0,
            "unit": "pcs",
            "reorder_threshold": 1.0,
        },
    )
    assert bad_response.status_code == 422


def test_suggest_recipe_endpoint_returns_escaped_card() -> None:
    """Verify POST /pantry/recipes/suggest returns a structured HTML recipe card."""
    _setup_isolated_db()
    client = TestClient(app)

    response = client.post("/pantry/recipes/suggest")
    assert response.status_code == 200
    assert 'id="generated-recipe-card"' in response.text
    assert "Chickpeas" in response.text
    assert "Baby Spinach" in response.text


if __name__ == "__main__":
    test_functions = [
        test_dashboard_renders_seeded_pantry_and_htmx_attributes,
        test_security_headers_enforced_on_all_responses,
        test_add_pantry_item_htmx_fragment_and_low_stock_flag,
        test_xss_payload_is_strictly_escaped_in_fragment_and_dashboard,
        test_invalid_category_or_negative_quantity_rejected,
        test_suggest_recipe_endpoint_returns_escaped_card,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 07 Web UI & Security tests passed!")

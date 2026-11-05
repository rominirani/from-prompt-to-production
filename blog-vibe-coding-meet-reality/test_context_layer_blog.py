"""Automated tests for the 'Vibe Coding, Meet Reality' Blog Post & Companion Codebase."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

BLOG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BLOG_DIR))

from context_layer_gateway import (
    ContextLayerGateway,
    RestockRequestPayload,
    create_seeded_roast_db,
    run_naive_direct_db_dashboard_query,
    validate_mcp_toolbox_yaml,
)
from knowledge_catalog_setup import (
    KnowledgeCatalogConfig,
    build_context_set_payload,
    build_glossary_and_table_entries,
    build_schema_join_links,
    simulate_lookup_context_yaml,
)
from single_pane_app import app, verify_no_direct_db_access


def test_naive_vs_governed_revenue_and_pii_protection() -> None:
    """Prove the Naive direct-to-DB query overstates revenue and leaks PII, while the Context Layer is exact and masked."""
    naive_result = run_naive_direct_db_dashboard_query(create_seeded_roast_db())
    # Naive query sums REFUNDED ($36.00) + CANCELLED ($28.50) + ignores $11.00 discounts = $258.00!
    assert naive_result["naive_reported_revenue_usd"] == Decimal("258.00")
    assert "@example.co.za" in naive_result["leaked_customer_records"][0]["email"]
    assert "+27-" in naive_result["leaked_customer_records"][0]["phone_number"]

    # Governed Context Layer calculates true Net Store Revenue ($182.50) and masks PII
    gateway = ContextLayerGateway()
    summaries = gateway.get_store_net_revenue_summary("ALL")
    total_governed_revenue = sum((s.net_revenue_usd for s in summaries), Decimal("0.00"))
    assert total_governed_revenue == Decimal("182.50")

    vip_orders = gateway.lookup_vip_orders_masked("GOLD")
    assert len(vip_orders) == 2
    for order in vip_orders:
        dumped = order.model_dump_json()
        assert "@example.co.za" not in dumped
        assert "+27-" not in dumped
        assert "Beach Rd" not in dumped
        assert order.customer_display_name in {"Thabo M.", "Anika N."}


def test_mcp_toolbox_yaml_governance_validation() -> None:
    """Verify `tools.yaml` uses `cloud-sql-postgres`, positional `$1` bindings, and selects zero forbidden columns."""
    tools_yaml = BLOG_DIR / "tools.yaml"
    report = validate_mcp_toolbox_yaml(tools_yaml)
    assert report["valid"] is True
    assert report["source_kind"] == "cloud-sql-postgres"
    assert set(report["tool_names"]) == {
        "get_store_net_revenue_summary",
        "get_low_stock_inventory_alerts",
        "lookup_vip_orders_masked",
        "create_bean_restock_request",
    }


def test_knowledge_catalog_context_set_and_links() -> None:
    """Verify Knowledge Catalog Context Set, Glossary entries, and `schema-join` links are well-formed."""
    cfg = KnowledgeCatalogConfig(project_id="roast-and-co-prod", location="us-central1")
    cs_payload = build_context_set_payload(cfg)
    assert cs_payload["type"] == "context-set"
    assert cs_payload["entryGroupId"] == "roast-and-co-context-set"

    entries = build_glossary_and_table_entries(cfg)
    assert len(entries) == 3
    links = build_schema_join_links(cfg)
    assert len(links) == 2
    assert links[1]["entryLinkType"].endswith("/schema-join")

    yaml_text = simulate_lookup_context_yaml(cfg)
    assert "SUM(gross_amount_usd - discount_usd)" in yaml_text
    assert "lookup_vip_orders_masked" in yaml_text


def test_single_pane_of_glass_fastapi_dashboard_and_audit_log() -> None:
    """Verify the Single-Pane-of-Glass dashboard renders clean HTML, enforces security headers, and records audit logs."""
    client = TestClient(app)

    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert "Roast &amp; Co. — Morning Franchise Pulse" in html_resp.text
    assert "$182.50" in html_resp.text
    assert "Thabo M." in html_resp.text
    assert "thabo.ms@example.co.za" not in html_resp.text
    assert html_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert html_resp.headers["X-Frame-Options"] == "DENY"

    restock_resp = client.post(
        "/api/restock",
        json={
            "store_id": "store-ct-01",
            "sku_id": "sku-eth-beans",
            "requested_quantity": "15.0",
            "requested_by": "cape-town-manager",
        },
    )
    assert restock_resp.status_code == 201
    assert restock_resp.json()["status"] == "restock_requested"

    audit_resp = client.get("/api/audit-log")
    assert audit_resp.status_code == 200
    assert audit_resp.json()["total_events"] >= 4


def test_ast_architectural_boundary_verifier() -> None:
    """Verify `single_pane_app.py` passes AST inspection while rogue direct-DB code is blocked."""
    app_source = (BLOG_DIR / "single_pane_app.py").read_text(encoding="utf-8")
    clean_check = verify_no_direct_db_access(app_source)
    assert clean_check["approved"] is True
    assert clean_check["violations"] == []

    rogue_vibe_coded_app = '''
import psycopg
from sqlalchemy import create_engine

def get_dashboard():
    query = "SELECT * FROM customers WHERE loyalty_tier = 'GOLD'"
    return query
'''
    rogue_check = verify_no_direct_db_access(rogue_vibe_coded_app)
    assert rogue_check["approved"] is False
    assert len(rogue_check["violations"]) == 3


if __name__ == "__main__":
    tests = [
        test_naive_vs_governed_revenue_and_pii_protection,
        test_mcp_toolbox_yaml_governance_validation,
        test_knowledge_catalog_context_set_and_links,
        test_single_pane_of_glass_fastapi_dashboard_and_audit_log,
        test_ast_architectural_boundary_verifier,
    ]
    for fn in tests:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print(f"\nAll {len(tests)}/{len(tests)} blog companion tests passed!")

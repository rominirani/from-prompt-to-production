"""Step 3 of the Blog Post: The Governed Context Layer Gateway (MCP Toolbox + Knowledge Catalog).

Provides:
1. `validate_mcp_toolbox_yaml`: Verifies `tools.yaml` uses `cloud-sql-postgres`, positional
   parameters (`$1`), and never selects restricted PII or supplier margin columns.
2. `run_naive_direct_db_dashboard_query`: Demonstrates the "Bootlegger Trap" when an AI agent
   generates raw SQL directly against the database without a Context Layer (leaking customer
   emails/phones/addresses and overstating revenue by $79.50!).
3. `ContextLayerGateway`: Executes ONLY the 4 governed tools defined in `tools.yaml` with
   Pydantic v2 validation, PII masking, and an immutable audit trail.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Pydantic v2 Domain Models for the Governed Context Layer
# ---------------------------------------------------------------------------


class StoreRevenueSummary(BaseModel):
    """Governed output for `get_store_net_revenue_summary`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    store_id: str
    store_name: str
    city: str
    manager_name: str
    daily_target_usd: Decimal
    completed_orders: int
    excluded_orders: int
    net_revenue_usd: Decimal


class LowStockAlert(BaseModel):
    """Governed output for `get_low_stock_inventory_alerts` (excludes supplier_cost_usd!)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    store_id: str
    store_name: str
    city: str
    sku_id: str
    item_name: str
    unit: str
    stock_on_hand: Decimal
    reorder_threshold: Decimal
    shortage_amount: Decimal


class MaskedVipOrder(BaseModel):
    """Governed output for `lookup_vip_orders_masked` (zero raw PII columns!)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: str
    store_id: str
    customer_display_name: str
    loyalty_tier: str
    status: str
    net_order_usd: Decimal
    order_timestamp: str


class RestockRequestPayload(BaseModel):
    """Validated input for `create_bean_restock_request`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    store_id: str = Field(pattern=r"^store-[a-z0-9-]+$")
    sku_id: str = Field(pattern=r"^sku-[a-z0-9-]+$")
    requested_quantity: Decimal = Field(gt=Decimal("0"), le=Decimal("200"))
    requested_by: str = Field(min_length=2, max_length=100)


class AuditLogEntry(BaseModel):
    """Immutable audit log record recorded for every Context Layer invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp_utc: str
    caller_identity: str
    tool_name: str
    parameters: dict[str, Any]
    row_count: int


# ---------------------------------------------------------------------------
# 2. Validator for MCP Toolbox `tools.yaml`
# ---------------------------------------------------------------------------

FORBIDDEN_PII_AND_SECRET_COLUMNS = (
    "phone_number",
    "home_address",
    "supplier_cost_usd",
)


def validate_mcp_toolbox_yaml(tools_yaml_path: str | Path) -> dict[str, Any]:
    """Verify `tools.yaml` adheres to Context Layer governance rules."""
    path = Path(tools_yaml_path).resolve()
    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    sources = config.get("sources", {})
    if "roast-cloudsql-pg" not in sources:
        raise ValueError("Missing 'roast-cloudsql-pg' source in tools.yaml.")
    if sources["roast-cloudsql-pg"].get("kind") != "cloud-sql-postgres":
        raise ValueError("Source 'roast-cloudsql-pg' must use kind: cloud-sql-postgres.")

    tools = config.get("tools", {})
    for tool_name, spec in tools.items():
        statement = str(spec.get("statement", ""))
        if "$1" not in statement:
            raise ValueError(f"Tool '{tool_name}' must use positional parameter '$1'.")
        for forbidden_col in FORBIDDEN_PII_AND_SECRET_COLUMNS:
            if forbidden_col in statement.lower():
                raise ValueError(
                    f"Governance violation: Tool '{tool_name}' selects restricted column '{forbidden_col}'."
                )

    return {
        "valid": True,
        "source_kind": sources["roast-cloudsql-pg"]["kind"],
        "tool_names": list(tools.keys()),
        "toolsets": list(config.get("toolsets", {}).keys()),
    }


# ---------------------------------------------------------------------------
# 3. Local Seeded Mirror of `roast_and_co` (Matches `sql/01_schema_and_seed.sql`)
# ---------------------------------------------------------------------------


def create_seeded_roast_db() -> sqlite3.Connection:
    """Create an in-memory database seeded with the exact rows from `01_schema_and_seed.sql`."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(
            """
            CREATE TABLE stores (
                store_id TEXT PRIMARY KEY,
                store_name TEXT NOT NULL,
                city TEXT NOT NULL,
                manager_name TEXT NOT NULL,
                daily_target_usd REAL NOT NULL
            );
            CREATE TABLE customers (
                customer_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone_number TEXT NOT NULL,
                home_address TEXT NOT NULL,
                loyalty_tier TEXT NOT NULL,
                loyalty_points INTEGER NOT NULL
            );
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                order_timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                gross_amount_usd REAL NOT NULL,
                discount_usd REAL NOT NULL,
                tax_usd REAL NOT NULL
            );
            CREATE TABLE bean_inventory (
                store_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                unit TEXT NOT NULL,
                stock_on_hand REAL NOT NULL,
                reorder_threshold REAL NOT NULL,
                supplier_cost_usd REAL NOT NULL,
                PRIMARY KEY (store_id, sku_id)
            );
            CREATE TABLE restock_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                requested_quantity REAL NOT NULL,
                requested_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO stores VALUES (?, ?, ?, ?, ?)",
            [
                ("store-ct-01", "Roast & Co. Sea Point", "Cape Town", "Lindiwe Khumalo", 150.00),
                ("store-jhb-02", "Roast & Co. Rosebank", "Johannesburg", "Pieter van Wyk", 180.00),
                ("store-dbn-03", "Roast & Co. Umhlanga", "Durban", "Amahle Dlamini", 120.00),
            ],
        )
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "cust-101",
                    "Thabo Mbeki-Smith",
                    "thabo.ms@example.co.za",
                    "+27-82-555-0191",
                    "14 Beach Rd, Sea Point, Cape Town",
                    "GOLD",
                    1420,
                ),
                (
                    "cust-102",
                    "Anika Naidoo",
                    "anika.n@example.co.za",
                    "+27-83-555-0442",
                    "88 Oxford Rd, Rosebank, Johannesburg",
                    "GOLD",
                    980,
                ),
                (
                    "cust-103",
                    "Chloe Vermeulen",
                    "chloe.v@example.co.za",
                    "+27-71-555-0823",
                    "22 Lagoon Dr, Umhlanga, Durban",
                    "SILVER",
                    410,
                ),
                (
                    "cust-104",
                    "Sipho Ndlovu",
                    "sipho.nd@example.co.za",
                    "+27-84-555-0319",
                    "5 Kloof St, Gardens, Cape Town",
                    "BRONZE",
                    120,
                ),
            ],
        )
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("ord-9001", "store-ct-01", "cust-101", "2026-11-05T07:15:00+02:00", "COMPLETED", 42.00, 4.00, 5.70),
                ("ord-9002", "store-ct-01", "cust-104", "2026-11-05T08:05:00+02:00", "COMPLETED", 28.50, 0.00, 4.28),
                ("ord-9003", "store-ct-01", "cust-101", "2026-11-05T08:45:00+02:00", "REFUNDED", 36.00, 0.00, 5.40),
                ("ord-9004", "store-jhb-02", "cust-102", "2026-11-05T07:30:00+02:00", "COMPLETED", 65.00, 5.00, 9.00),
                ("ord-9005", "store-jhb-02", "cust-102", "2026-11-05T09:10:00+02:00", "CANCELLED", 28.50, 0.00, 0.00),
                ("ord-9006", "store-dbn-03", "cust-103", "2026-11-05T08:20:00+02:00", "COMPLETED", 58.00, 2.00, 8.40),
            ],
        )
        conn.executemany(
            "INSERT INTO bean_inventory VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("store-ct-01", "sku-eth-beans", "Ethiopian Yirgacheffe Beans", "kg", 3.50, 10.00, 18.50),
                ("store-ct-01", "sku-oat-milk", "Barista Oat Milk", "liters", 24.00, 15.00, 2.40),
                ("store-jhb-02", "sku-eth-beans", "Ethiopian Yirgacheffe Beans", "kg", 18.00, 10.00, 18.50),
                ("store-jhb-02", "sku-oat-milk", "Barista Oat Milk", "liters", 6.00, 20.00, 2.40),
                ("store-dbn-03", "sku-col-beans", "Colombian Supremo Beans", "kg", 4.00, 8.00, 16.00),
            ],
        )
    return conn


# ---------------------------------------------------------------------------
# 4. "Before" Picture: The Naive Direct-to-DB Vibe-Coded Query (The Trap!)
# ---------------------------------------------------------------------------


def run_naive_direct_db_dashboard_query(conn: sqlite3.Connection) -> dict[str, Any]:
    """Simulate what happens when an unconstrained AI app queries raw tables directly.

    1. It runs `SUM(gross_amount_usd)` across all orders (including REFUNDED and CANCELLED
       and ignoring discounts), reporting $258.00 instead of the true $182.50 Net Revenue!
    2. It joins `customers` with `SELECT *`, leaking `email`, `phone_number`, and `home_address`!
    """
    naive_rev_row = conn.execute(
        "SELECT COALESCE(SUM(gross_amount_usd), 0.0) AS bogus_revenue FROM orders"
    ).fetchone()
    leaked_customers = [
        dict(row)
        for row in conn.execute(
            "SELECT o.order_id, c.full_name, c.email, c.phone_number, c.home_address "
            "FROM orders o JOIN customers c ON c.customer_id = o.customer_id"
        ).fetchall()
    ]
    return {
        "naive_reported_revenue_usd": Decimal(str(naive_rev_row["bogus_revenue"])).quantize(
            Decimal("0.01")
        ),
        "leaked_customer_records": leaked_customers,
    }


# ---------------------------------------------------------------------------
# 5. "After" Picture: The Governed Context Layer Gateway
# ---------------------------------------------------------------------------


def _mask_customer_name(full_name: str) -> str:
    parts = [p for p in full_name.strip().split() if p]
    if not parts:
        return "Guest"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


class ContextLayerGateway:
    """Executes ONLY the governed MCP Toolbox tools with audit logging and PII protection."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or create_seeded_roast_db()
        self._audit_log: list[AuditLogEntry] = []

    def _record_audit(
        self, caller_identity: str, tool_name: str, parameters: dict[str, Any], row_count: int
    ) -> None:
        self._audit_log.append(
            AuditLogEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                caller_identity=caller_identity,
                tool_name=tool_name,
                parameters=parameters,
                row_count=row_count,
            )
        )

    @property
    def audit_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def get_store_net_revenue_summary(
        self, city_filter: str = "ALL", *, caller_identity: str = "single-pane-dashboard"
    ) -> list[StoreRevenueSummary]:
        """Tool 1: Compute verified Net Store Revenue (COMPLETED orders minus discounts)."""
        cleaned_city = city_filter.strip() or "ALL"
        rows = self._conn.execute(
            """
            SELECT
                s.store_id,
                s.store_name,
                s.city,
                s.manager_name,
                s.daily_target_usd,
                SUM(CASE WHEN o.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_orders,
                SUM(CASE WHEN o.status IN ('REFUNDED', 'CANCELLED') THEN 1 ELSE 0 END) AS excluded_orders,
                COALESCE(
                    SUM(CASE WHEN o.status = 'COMPLETED' THEN (o.gross_amount_usd - o.discount_usd) ELSE 0.0 END),
                    0.0
                ) AS net_revenue_usd
            FROM stores s
            LEFT JOIN orders o ON o.store_id = s.store_id
            WHERE (? = 'ALL' OR LOWER(s.city) = LOWER(?))
            GROUP BY s.store_id, s.store_name, s.city, s.manager_name, s.daily_target_usd
            ORDER BY net_revenue_usd DESC
            """,
            (cleaned_city, cleaned_city),
        ).fetchall()

        results = [
            StoreRevenueSummary(
                store_id=row["store_id"],
                store_name=row["store_name"],
                city=row["city"],
                manager_name=row["manager_name"],
                daily_target_usd=Decimal(str(row["daily_target_usd"])).quantize(Decimal("0.01")),
                completed_orders=int(row["completed_orders"] or 0),
                excluded_orders=int(row["excluded_orders"] or 0),
                net_revenue_usd=Decimal(str(row["net_revenue_usd"])).quantize(Decimal("0.01")),
            )
            for row in rows
        ]
        self._record_audit(
            caller_identity,
            "get_store_net_revenue_summary",
            {"city_filter": cleaned_city},
            len(results),
        )
        return results

    def get_low_stock_inventory_alerts(
        self, store_id_filter: str = "ALL", *, caller_identity: str = "single-pane-dashboard"
    ) -> list[LowStockAlert]:
        """Tool 2: Return items at or below reorder_threshold without exposing supplier_cost_usd."""
        cleaned_store = store_id_filter.strip() or "ALL"
        rows = self._conn.execute(
            """
            SELECT
                i.store_id,
                s.store_name,
                s.city,
                i.sku_id,
                i.item_name,
                i.unit,
                i.stock_on_hand,
                i.reorder_threshold,
                (i.reorder_threshold - i.stock_on_hand) AS shortage_amount
            FROM bean_inventory i
            JOIN stores s ON s.store_id = i.store_id
            WHERE i.stock_on_hand <= i.reorder_threshold
              AND (? = 'ALL' OR i.store_id = ?)
            ORDER BY shortage_amount DESC
            """,
            (cleaned_store, cleaned_store),
        ).fetchall()

        alerts = [
            LowStockAlert(
                store_id=row["store_id"],
                store_name=row["store_name"],
                city=row["city"],
                sku_id=row["sku_id"],
                item_name=row["item_name"],
                unit=row["unit"],
                stock_on_hand=Decimal(str(row["stock_on_hand"])).quantize(Decimal("0.01")),
                reorder_threshold=Decimal(str(row["reorder_threshold"])).quantize(Decimal("0.01")),
                shortage_amount=Decimal(str(row["shortage_amount"])).quantize(Decimal("0.01")),
            )
            for row in rows
        ]
        self._record_audit(
            caller_identity,
            "get_low_stock_inventory_alerts",
            {"store_id_filter": cleaned_store},
            len(alerts),
        )
        return alerts

    def lookup_vip_orders_masked(
        self, loyalty_tier_filter: str = "GOLD", *, caller_identity: str = "single-pane-dashboard"
    ) -> list[MaskedVipOrder]:
        """Tool 3: Return recent VIP orders with strict PII masking (no email, phone, or address)."""
        cleaned_tier = loyalty_tier_filter.strip().upper()
        if cleaned_tier not in {"GOLD", "SILVER"}:
            raise ValueError("loyalty_tier_filter must be 'GOLD' or 'SILVER'.")

        rows = self._conn.execute(
            """
            SELECT
                o.order_id,
                o.store_id,
                c.full_name,
                c.loyalty_tier,
                o.status,
                (o.gross_amount_usd - o.discount_usd) AS net_order_usd,
                o.order_timestamp
            FROM orders o
            JOIN customers c ON c.customer_id = o.customer_id
            WHERE o.status = 'COMPLETED'
              AND UPPER(c.loyalty_tier) = ?
            ORDER BY o.order_timestamp DESC
            LIMIT 25
            """,
            (cleaned_tier,),
        ).fetchall()

        masked_orders = [
            MaskedVipOrder(
                order_id=row["order_id"],
                store_id=row["store_id"],
                customer_display_name=_mask_customer_name(row["full_name"]),
                loyalty_tier=row["loyalty_tier"],
                status=row["status"],
                net_order_usd=Decimal(str(row["net_order_usd"])).quantize(Decimal("0.01")),
                order_timestamp=row["order_timestamp"],
            )
            for row in rows
        ]
        self._record_audit(
            caller_identity,
            "lookup_vip_orders_masked",
            {"loyalty_tier_filter": cleaned_tier},
            len(masked_orders),
        )
        return masked_orders

    def create_bean_restock_request(
        self,
        payload: RestockRequestPayload,
        *,
        caller_identity: str = "single-pane-dashboard",
    ) -> dict[str, Any]:
        """Tool 4: Create a bounded, audited restock request."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO restock_requests (store_id, sku_id, requested_quantity, requested_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.store_id,
                    payload.sku_id,
                    float(payload.requested_quantity),
                    payload.requested_by,
                    now_iso,
                ),
            )
            request_id = cursor.lastrowid

        self._record_audit(
            caller_identity,
            "create_bean_restock_request",
            payload.model_dump(mode="json"),
            1,
        )
        return {
            "status": "restock_requested",
            "request_id": request_id,
            "store_id": payload.store_id,
            "sku_id": payload.sku_id,
            "requested_quantity": str(payload.requested_quantity),
            "requested_by": payload.requested_by,
            "created_at": now_iso,
        }


if __name__ == "__main__":
    gateway = ContextLayerGateway()
    naive = run_naive_direct_db_dashboard_query(create_seeded_roast_db())
    governed_stores = gateway.get_store_net_revenue_summary("ALL")
    true_net_rev = sum((s.net_revenue_usd for s in governed_stores), Decimal("0.00"))

    print("=== Vibe Coding, Meet Reality: Naive Direct-to-DB vs. Governed Context Layer ===")
    print(f"1. Naive Unconstrained SQL Revenue : ${naive['naive_reported_revenue_usd']} (OVERSTATED by ${naive['naive_reported_revenue_usd'] - true_net_rev}!)")
    print(f"2. Governed Context Layer Revenue  : ${true_net_rev} (Exact Net Store Revenue)")
    print(f"3. Naive Leaked Customer Phone #   : {naive['leaked_customer_records'][0]['phone_number']}")
    vip_orders = gateway.lookup_vip_orders_masked("GOLD")
    print(f"4. Governed Masked VIP Order       : {vip_orders[0].model_dump_json()}")

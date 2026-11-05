-- =============================================================================
-- Roast & Co. Coffee Franchise — Cloud SQL for PostgreSQL Schema & Seed Data
-- Companion SQL for: "Vibe Coding, Meet Reality: Building a Governed Context
-- Layer with Cloud SQL, Google Cloud Knowledge Catalog & MCP Toolbox"
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS restock_requests CASCADE;
DROP TABLE IF EXISTS bean_inventory CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS stores CASCADE;

-- 1. Franchise Stores
CREATE TABLE stores (
    store_id VARCHAR(32) PRIMARY KEY,
    store_name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL,
    manager_name VARCHAR(100) NOT NULL,
    daily_target_usd NUMERIC(10, 2) NOT NULL CHECK (daily_target_usd >= 0)
);

-- 2. Loyalty Customers (CONTAINS THE PII TRAP: email, phone_number, home_address)
CREATE TABLE customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(160) NOT NULL UNIQUE,
    phone_number VARCHAR(40) NOT NULL,
    home_address TEXT NOT NULL,
    loyalty_tier VARCHAR(20) NOT NULL CHECK (loyalty_tier IN ('BRONZE', 'SILVER', 'GOLD')),
    loyalty_points INTEGER NOT NULL DEFAULT 0 CHECK (loyalty_points >= 0)
);

-- 3. Customer Orders (CONTAINS THE BUSINESS LOGIC TRAP: REFUNDED & CANCELLED rows)
-- Business Rule in Knowledge Catalog:
--   Net Store Revenue = SUM(gross_amount_usd - discount_usd) WHERE status = 'COMPLETED'
CREATE TABLE orders (
    order_id VARCHAR(32) PRIMARY KEY,
    store_id VARCHAR(32) NOT NULL REFERENCES stores(store_id),
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(customer_id),
    order_timestamp TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('COMPLETED', 'REFUNDED', 'CANCELLED')),
    gross_amount_usd NUMERIC(10, 2) NOT NULL CHECK (gross_amount_usd >= 0),
    discount_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (discount_usd >= 0),
    tax_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (tax_usd >= 0)
);

-- 4. Store Bean & Milk Inventory (CONTAINS WHOLESALE SUPPLIER COST)
CREATE TABLE bean_inventory (
    store_id VARCHAR(32) NOT NULL REFERENCES stores(store_id),
    sku_id VARCHAR(32) NOT NULL,
    item_name VARCHAR(120) NOT NULL,
    unit VARCHAR(20) NOT NULL CHECK (unit IN ('kg', 'liters', 'boxes')),
    stock_on_hand NUMERIC(10, 2) NOT NULL CHECK (stock_on_hand >= 0),
    reorder_threshold NUMERIC(10, 2) NOT NULL CHECK (reorder_threshold >= 0),
    supplier_cost_usd NUMERIC(10, 2) NOT NULL CHECK (supplier_cost_usd >= 0),
    PRIMARY KEY (store_id, sku_id)
);

-- 5. Governed Restock Requests (Created via MCP Toolbox action tool)
CREATE TABLE restock_requests (
    request_id SERIAL PRIMARY KEY,
    store_id VARCHAR(32) NOT NULL REFERENCES stores(store_id),
    sku_id VARCHAR(32) NOT NULL,
    requested_quantity NUMERIC(10, 2) NOT NULL CHECK (requested_quantity > 0 AND requested_quantity <= 200),
    requested_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Seed Data
-- =============================================================================

INSERT INTO stores (store_id, store_name, city, manager_name, daily_target_usd) VALUES
    ('store-ct-01',  'Roast & Co. Sea Point',   'Cape Town',    'Lindiwe Khumalo', 150.00),
    ('store-jhb-02', 'Roast & Co. Rosebank',    'Johannesburg', 'Pieter van Wyk',  180.00),
    ('store-dbn-03', 'Roast & Co. Umhlanga',    'Durban',       'Amahle Dlamini',  120.00);

INSERT INTO customers (customer_id, full_name, email, phone_number, home_address, loyalty_tier, loyalty_points) VALUES
    ('cust-101', 'Thabo Mbeki-Smith', 'thabo.ms@example.co.za',  '+27-82-555-0191', '14 Beach Rd, Sea Point, Cape Town',     'GOLD',   1420),
    ('cust-102', 'Anika Naidoo',      'anika.n@example.co.za',   '+27-83-555-0442', '88 Oxford Rd, Rosebank, Johannesburg',  'GOLD',    980),
    ('cust-103', 'Chloe Vermeulen',   'chloe.v@example.co.za',   '+27-71-555-0823', '22 Lagoon Dr, Umhlanga, Durban',        'SILVER',  410),
    ('cust-104', 'Sipho Ndlovu',      'sipho.nd@example.co.za',  '+27-84-555-0319', '5 Kloof St, Gardens, Cape Town',        'BRONZE',  120);

-- Notice the refunded and cancelled orders below:
-- Naive SUM(gross_amount_usd) across all rows = $258.00 (Overstated by $75.50!)
-- True Net Store Revenue = SUM(gross_amount_usd - discount_usd) WHERE status = 'COMPLETED' = $182.50
INSERT INTO orders (order_id, store_id, customer_id, order_timestamp, status, gross_amount_usd, discount_usd, tax_usd) VALUES
    ('ord-9001', 'store-ct-01',  'cust-101', '2026-11-05 07:15:00+02', 'COMPLETED', 42.00,  4.00, 5.70),
    ('ord-9002', 'store-ct-01',  'cust-104', '2026-11-05 08:05:00+02', 'COMPLETED', 28.50,  0.00, 4.28),
    ('ord-9003', 'store-ct-01',  'cust-101', '2026-11-05 08:45:00+02', 'REFUNDED',  36.00,  0.00, 5.40),
    ('ord-9004', 'store-jhb-02', 'cust-102', '2026-11-05 07:30:00+02', 'COMPLETED', 65.00,  5.00, 9.00),
    ('ord-9005', 'store-jhb-02', 'cust-102', '2026-11-05 09:10:00+02', 'CANCELLED', 28.50,  0.00, 0.00),
    ('ord-9006', 'store-dbn-03', 'cust-103', '2026-11-05 08:20:00+02', 'COMPLETED', 58.00,  2.00, 8.40);

INSERT INTO bean_inventory (store_id, sku_id, item_name, unit, stock_on_hand, reorder_threshold, supplier_cost_usd) VALUES
    ('store-ct-01',  'sku-eth-beans', 'Ethiopian Yirgacheffe Beans', 'kg',     3.50, 10.00, 18.50),
    ('store-ct-01',  'sku-oat-milk',  'Barista Oat Milk',            'liters', 24.00, 15.00, 2.40),
    ('store-jhb-02', 'sku-eth-beans', 'Ethiopian Yirgacheffe Beans', 'kg',    18.00, 10.00, 18.50),
    ('store-jhb-02', 'sku-oat-milk',  'Barista Oat Milk',            'liters',  6.00, 20.00, 2.40),
    ('store-dbn-03', 'sku-col-beans', 'Colombian Supremo Beans',     'kg',     4.00,  8.00, 16.00);

COMMIT;

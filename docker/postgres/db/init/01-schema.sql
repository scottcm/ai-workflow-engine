-- =========================================================
-- Test Schema for AI Workflow Engine (PostgreSQL 16)
-- Generic multi-tenant example:
--   - app.tenants       : tenant entity itself
--   - global.tiers      : global/shared lookup
--   - app.products      : tenant-scoped table with RLS
-- =========================================================

-- Extension for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Schemas
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS global;

-- =========================================================
-- 1) Tenant Entity (the tenant itself)
-- =========================================================
CREATE TABLE app.tenants (
    id          BIGSERIAL PRIMARY KEY,
    public_id   UUID UNIQUE NOT NULL,
    code        VARCHAR(50) UNIQUE NOT NULL,    -- short, human-friendly identifier
    name        VARCHAR(200) NOT NULL,          -- display name
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    version     BIGINT DEFAULT 0 NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE NOT NULL
);

-- =========================================================
-- 2) Global / Shared Table (no tenant_id)
-- =========================================================
CREATE TABLE global.tiers (
    id          BIGSERIAL PRIMARY KEY,
    public_id   UUID UNIQUE NOT NULL,
    code        VARCHAR(50) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    version     BIGINT DEFAULT 0 NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE NOT NULL
);

-- =========================================================
-- 3) Tenant-Scoped Table (has tenant_id and global FK)
-- =========================================================
CREATE TABLE app.products (
    id          BIGSERIAL PRIMARY KEY,
    public_id   UUID UNIQUE NOT NULL,
    tenant_id   BIGINT NOT NULL REFERENCES app.tenants(id),
    tier_id     BIGINT REFERENCES global.tiers(id),
    sku         VARCHAR(100) NOT NULL,
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    price       NUMERIC(10,2),
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    version     BIGINT DEFAULT 0 NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE NOT NULL,

    -- Example of tenant-scoped uniqueness
    UNIQUE (tenant_id, sku)
);

-- =========================================================
-- 4) Row-Level Security (RLS) for tenant-scoped table
-- =========================================================
ALTER TABLE app.products ENABLE ROW LEVEL SECURITY;

-- The application is expected to set, per connection:
--   SET LOCAL app.current_tenant_id = '<tenant id>';
CREATE POLICY tenant_isolation_policy
ON app.products
USING (tenant_id = current_setting('app.current_tenant_id', true)::BIGINT);

-- =========================================================
-- 5) Generic updated_at triggers
-- =========================================================
CREATE OR REPLACE FUNCTION app._touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_products_updated_at
    BEFORE UPDATE ON app.products
    FOR EACH ROW
    EXECUTE FUNCTION app._touch_updated_at();

CREATE TRIGGER trigger_tenants_updated_at
    BEFORE UPDATE ON app.tenants
    FOR EACH ROW
    EXECUTE FUNCTION app._touch_updated_at();

CREATE TRIGGER trigger_tiers_updated_at
    BEFORE UPDATE ON global.tiers
    FOR EACH ROW
    EXECUTE FUNCTION app._touch_updated_at();

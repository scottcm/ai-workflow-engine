-- Mock DDL Schema for E2E Testing
-- This represents a simple "Tier" entity in a multi-tenant system

CREATE TABLE global.tiers (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- This is a global reference table (no tenant_id column)
-- Classification: Global Reference Data

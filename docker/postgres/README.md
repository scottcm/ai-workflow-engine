# Postgres Test Database

This directory contains the Docker configuration and initialization scripts for
the PostgreSQL database used to test AI-generated code produced by the AI Workflow Engine.

The goal of this database is to provide a **small but realistic** multi-tenant schema
that exercises:

- Tenant entity modeling
- Global/shared lookup tables
- Tenant-scoped tables
- Row-Level Security (RLS)
- `updated_at` triggers

It is not a production schema; it is a stable, reproducible target for code generation
and integration tests.

---

## Directory Layout

```text
docker/postgres/
├── docker-compose.yml
└── db/
    └── init/
        ├── 01-schema.sql   # Creates schemas, tables, RLS, triggers
        └── 02-seed.sql     # Inserts sample tenants, tiers, products
```

- All `.sql` files in `db/init/` are executed automatically by the official
  Postgres image on first container startup.
- The database data itself is stored in a Docker named volume
  (`aiwf_pgdata`), not in the repository.

---

## How to Start the Database

From the project root:

    cd docker/postgres
    docker compose up -d

This will:

1. Start a PostgreSQL 16 container
2. Create the `aiwf_test` database
3. Run `01-schema.sql` to create schemas, tables, and RLS/trigger functions
4. Run `02-seed.sql` to insert sample data

The first startup will take slightly longer while the database is initialized.

---

## How to Stop and Reset the Database

To stop the database **without** destroying data:

    cd docker/postgres
    docker compose down

To stop the database **and delete all data** (fresh re-init on next start):

    cd docker/postgres
    docker compose down -v

On the next `docker compose up -d`, the init scripts will run again and
recreate the schema + seed data from scratch.

---

## Connection Details

Default connection parameters:

- Host: `localhost`
- Port: `5432`
- Database: `aiwf_test`
- User: `aiwf_user`
- Password: `aiwf_pass`

These values are defined in `docker-compose.yml` and can be overridden if needed.

Example `psql` connection from the host:

    psql "postgresql://aiwf_user:aiwf_pass@localhost:5432/aiwf_test"

---

## Schema Overview

The schema is intentionally small but representative of common multi-tenant patterns.

### Schemas

- `app` – tenant entities and tenant-scoped tables
- `global` – shared/global lookup tables

### Tables

- `app.tenants`  
  - Represents the tenant itself (one row per tenant)
  - Columns: `id`, `public_id`, `code`, `name`, `created_at`, `updated_at`, `version`, `is_active`
  - No RLS (typically accessed via an admin connection)

- `global.tiers`  
  - Global/shared lookup table (e.g., free/pro/enterprise tiers)
  - Columns: `id`, `public_id`, `code`, `name`, `description`, `created_at`, `updated_at`, `version`, `is_active`
  - No RLS (same for all tenants)

- `app.products`  
  - Tenant-scoped table with foreign keys to `app.tenants` and `global.tiers`
  - Columns: `id`, `public_id`, `tenant_id`, `tier_id`, `sku`, `name`, `description`, `price`, `created_at`, `updated_at`, `version`, `is_active`
  - Enforces `UNIQUE (tenant_id, sku)`
  - Has RLS enabled

### Row-Level Security

`app.products` uses a simple tenant isolation policy:

- RLS is enabled on `app.products`
- Policy checks that `tenant_id` matches the current session setting:

  - `app.current_tenant_id` (text) is cast to `BIGINT`
  - The application or test harness is expected to execute:
    
        SET LOCAL app.current_tenant_id = '<tenant id>';

### Triggers

All three tables (`app.tenants`, `global.tiers`, `app.products`) share a common
`updated_at` trigger:

- Function: `app._touch_updated_at()`
- Behavior: set `NEW.updated_at = NOW()` on every `UPDATE`
- Trigger names:
  - `trigger_tenants_updated_at`
  - `trigger_tiers_updated_at`
  - `trigger_products_updated_at`

This keeps `updated_at` consistent without requiring explicit handling in application code.

---

## Seed Data

`02-seed.sql` inserts a small, deterministic dataset suitable for testing:

- Tenants:
  - `tenant_alpha` (`Tenant Alpha`)
  - `tenant_beta` (`Tenant Beta`)

- Tiers (global):
  - `FREE` – Free Tier
  - `PRO` – Pro Tier
  - `ENTER` – Enterprise Tier

- Products:
  - One product per `(tenant, tier)` combination
  - `sku` format: `SKU-<tenant_code>-<tier_code>`
  - Example: `SKU-tenant_alpha-FREE`

This gives you:

- Multiple tenants
- Multiple tiers
- Multiple products per tenant
- A realistic dataset for RLS and repository queries

---

## Usage in the AI Workflow Engine

This database exists to support:

- Code generation tests for the `jpa-mt` profile
- Validation of JPA entity + repository mappings against a real schema
- RLS behavior verification for tenant-scoped tables
- Integration tests that demonstrate the full workflow:
  - Generate domain layer code (entities + repositories)
  - Compile and run tests against this database

The schema is intentionally stable so prompt templates, standards, and tests
can all assume its shape.

If the schema changes in the future, update:

1. `01-schema.sql`
2. `02-seed.sql`
3. Any corresponding tests or profile standards that depend on specific tables/columns.

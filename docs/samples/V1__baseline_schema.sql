-- =====================================================
-- V1: Control Plane Baseline Schema
-- =====================================================
-- Multi-tenant SaaS control plane for training platform
--
--
-- Architecture:
--   - Single control plane database
--   - Row-Level Security (RLS) for tenant isolation
--   - Each client has separate training database
--   - SSO-only authentication (no local passwords)
--
-- RLS Context Setting:
--   Use single connection pool with session variable:
--   SET LOCAL app.current_client_id = <client_id>
--
-- TODO Before Production:
--   - Encrypt client_databases.db_password (Phase 1B)
--   - Set up secrets manager for encryption keys
--   - Security audit of RLS policies
-- =====================================================

-- Schemas & extensions
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS global;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =====================================================
-- GLOBAL: Product Catalog (Cross-tenant reference data)
-- =====================================================

CREATE TABLE IF NOT EXISTS global.skus (
                                           id             BIGSERIAL PRIMARY KEY,
                                           public_id      UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    code           TEXT        NOT NULL UNIQUE,
    name           TEXT        NOT NULL,
    description    TEXT,
    category       TEXT,
    metering_unit  TEXT,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version        BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_skus_code_not_blank CHECK (length(btrim(code)) > 0),
    CONSTRAINT ck_skus_name_not_blank CHECK (length(btrim(name)) > 0)
    );

COMMENT ON TABLE global.skus IS 'Product SKUs - features and capabilities';
COMMENT ON COLUMN global.skus.metering_unit IS 'Unit for usage tracking (seat, gb, etc.)';

CREATE TABLE IF NOT EXISTS global.tiers (
                                            id           BIGSERIAL PRIMARY KEY,
                                            public_id    UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    code         TEXT        NOT NULL UNIQUE,
    name         TEXT        NOT NULL,
    description  TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version      BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_tiers_code_not_blank CHECK (length(btrim(code)) > 0),
    CONSTRAINT ck_tiers_name_not_blank CHECK (length(btrim(name)) > 0)
    );

COMMENT ON TABLE global.tiers IS 'Membership tiers/plans (Free, Pro, Enterprise)';

CREATE TABLE IF NOT EXISTS global.tier_skus (
                                                tier_id        BIGINT  NOT NULL REFERENCES global.tiers(id) ON DELETE CASCADE,
    sku_id         BIGINT  NOT NULL REFERENCES global.skus(id)  ON DELETE RESTRICT,
    quantity_limit INTEGER,
    required       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT pk_tier_skus PRIMARY KEY (tier_id, sku_id),
    CONSTRAINT ck_tier_skus_qty_nonneg CHECK (quantity_limit IS NULL OR quantity_limit >= 0)
    );

CREATE INDEX IF NOT EXISTS idx_tier_skus_sku ON global.tier_skus(sku_id);

COMMENT ON TABLE global.tier_skus IS 'Maps tiers to included SKUs with optional quantity limits';

-- =====================================================
-- APP: Tenant/Client Data
-- =====================================================

CREATE TABLE IF NOT EXISTS app.clients (
                                           id             BIGSERIAL PRIMARY KEY,
                                           public_id      UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    org_name       TEXT        NOT NULL,
    contact_email  TEXT        NOT NULL,
    contact_name   TEXT,
    timezone       TEXT        DEFAULT 'UTC',
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version        BIGINT      NOT NULL DEFAULT 0,
    owner_user_id BIGINT NULL,

    CONSTRAINT ck_clients_org_name_not_blank
    CHECK (length(btrim(org_name)) > 0),
    CONSTRAINT ck_clients_contact_email_format
    CHECK (contact_email IS NULL OR contact_email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
    );

CREATE INDEX IF NOT EXISTS idx_clients_email ON app.clients(lower(contact_email));
CREATE INDEX IF NOT EXISTS idx_clients_active ON app.clients(is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_clients_owner_user ON app.clients(owner_user_id);

COMMENT ON TABLE app.clients IS 'Tenant organizations';

CREATE TABLE IF NOT EXISTS app.client_databases (
                                                    id                    BIGSERIAL PRIMARY KEY,
                                                    public_id             UUID    NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id             BIGINT  NOT NULL UNIQUE REFERENCES app.clients(id) ON DELETE CASCADE,
    db_host               TEXT    NOT NULL,
    db_port               INTEGER NOT NULL DEFAULT 5432,
    db_name               TEXT    NOT NULL,
    db_username           TEXT    NOT NULL,
    db_password           TEXT    NOT NULL,
    max_pool_size         INTEGER DEFAULT 10,
    connection_timeout_ms INTEGER DEFAULT 30000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version               BIGINT  NOT NULL DEFAULT 0,

    CONSTRAINT ck_client_db_port_valid CHECK (db_port BETWEEN 1 AND 65535),
    CONSTRAINT ck_client_db_pool_size_positive CHECK (max_pool_size > 0),
    CONSTRAINT ck_client_db_timeout_positive CHECK (connection_timeout_ms > 0)
    );

CREATE INDEX IF NOT EXISTS idx_client_databases_client ON app.client_databases(client_id);

COMMENT ON TABLE app.client_databases IS 'Training database connection info per client';
COMMENT ON COLUMN app.client_databases.db_password IS 'TODO: Encrypt before production (Phase 1B)';

CREATE TABLE IF NOT EXISTS app.client_tiers (
                                                id             BIGSERIAL PRIMARY KEY,
                                                public_id      UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id      BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    tier_id        BIGINT      NOT NULL REFERENCES global.tiers(id) ON DELETE RESTRICT,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to   TIMESTAMPTZ,
    assigned_by    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version        BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_client_tiers_range_valid
    CHECK (effective_to IS NULL OR effective_to > effective_from)
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_client_tiers_current
    ON app.client_tiers(client_id) WHERE effective_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_client_tiers_client_time
    ON app.client_tiers(client_id, effective_from DESC);

CREATE INDEX IF NOT EXISTS idx_client_tiers_active_window
    ON app.client_tiers(client_id, effective_from DESC, effective_to)
    WHERE effective_to IS NULL;

COMMENT ON TABLE app.client_tiers IS 'Client tier assignments with time windows';

CREATE TABLE IF NOT EXISTS app.client_addons (
                                                 id             BIGSERIAL PRIMARY KEY,
                                                 public_id      UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id      BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    sku_id         BIGINT      NOT NULL REFERENCES global.skus(id) ON DELETE RESTRICT,
    quantity       INTEGER     NOT NULL DEFAULT 1,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to   TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version        BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_client_addons_qty_positive CHECK (quantity > 0),
    CONSTRAINT ck_client_addons_range_valid
    CHECK (effective_to IS NULL OR effective_to > effective_from)
    );

CREATE INDEX IF NOT EXISTS idx_client_addons_client_sku
    ON app.client_addons(client_id, sku_id);

CREATE INDEX IF NOT EXISTS idx_client_addons_active
    ON app.client_addons(client_id, effective_from, effective_to)
    WHERE effective_to IS NULL;

COMMENT ON TABLE app.client_addons IS 'Additional SKUs beyond tier inclusions';

-- =====================================================
-- Identity & Authentication (SSO Only)
-- =====================================================

CREATE TABLE IF NOT EXISTS app.identity_providers (
                                                      id              BIGSERIAL PRIMARY KEY,
                                                      public_id       UUID                NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    protocol        VARCHAR NOT NULL DEFAULT 'OIDC',
    name            TEXT,
    issuer          TEXT                NOT NULL UNIQUE,
    jwks_uri        TEXT,
    oauth_client_id TEXT,
    saml_entity_id  TEXT,
    saml_sso_url    TEXT,
    metadata        JSONB,
    is_active       BOOLEAN             NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version         BIGINT              NOT NULL DEFAULT 0
    );

CREATE INDEX IF NOT EXISTS idx_idp_issuer ON app.identity_providers(issuer);
CREATE INDEX IF NOT EXISTS idx_idp_active ON app.identity_providers(is_active) WHERE is_active;

COMMENT ON TABLE app.identity_providers IS 'SSO identity providers (Okta, Azure AD, Google)';

CREATE TABLE IF NOT EXISTS app.client_identity_providers (
                                                             id              BIGSERIAL PRIMARY KEY,
                                                             public_id       UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id       BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    provider_id     BIGINT      NOT NULL REFERENCES app.identity_providers(id) ON DELETE RESTRICT,
    is_primary      BOOLEAN     NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    oauth_client_id TEXT,
    metadata        JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version         BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT uq_cip_client_provider UNIQUE (client_id, provider_id),
    CONSTRAINT ck_cip_primary_implies_active CHECK (NOT is_primary OR is_active)
    );

CREATE INDEX IF NOT EXISTS idx_cip_client ON app.client_identity_providers(client_id);
CREATE INDEX IF NOT EXISTS idx_cip_provider ON app.client_identity_providers(provider_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cip_one_primary_per_client
    ON app.client_identity_providers(client_id) WHERE is_primary;

COMMENT ON TABLE app.client_identity_providers IS 'Maps clients to SSO providers';

CREATE TABLE IF NOT EXISTS app.identities (
                                              id            BIGSERIAL PRIMARY KEY,
                                              public_id     UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    provider_id   BIGINT      NOT NULL REFERENCES app.identity_providers(id) ON DELETE RESTRICT,
    subject       TEXT        NOT NULL,
    email         TEXT,
    display_name  TEXT,
    external_ref  JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version       BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT uq_identities_provider_subject UNIQUE (provider_id, subject),
    CONSTRAINT ck_identities_email_format
    CHECK (email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
    );

CREATE INDEX IF NOT EXISTS idx_identities_provider ON app.identities(provider_id);
CREATE INDEX IF NOT EXISTS idx_identities_email ON app.identities(lower(email));
CREATE INDEX IF NOT EXISTS idx_identities_external_ref_gin ON app.identities USING GIN(external_ref);

COMMENT ON TABLE app.identities IS 'External identities from SSO providers';

CREATE TABLE IF NOT EXISTS app.client_domains (
                                                  id          BIGSERIAL PRIMARY KEY,
                                                  public_id   UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id   BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    domain      TEXT        NOT NULL,
    verified    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version     BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_domain_not_blank CHECK (length(btrim(domain)) > 0),
    CONSTRAINT ck_domain_no_space CHECK (position(' ' in domain) = 0)
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_client_domains_domain_lower ON app.client_domains(lower(domain));
CREATE INDEX IF NOT EXISTS idx_client_domains_client ON app.client_domains(client_id);
CREATE INDEX IF NOT EXISTS idx_client_domains_verified ON app.client_domains(verified) WHERE verified;

COMMENT ON TABLE app.client_domains IS 'Verified email domains for client routing';

-- =====================================================
-- Users & Authorization
-- =====================================================

CREATE TABLE IF NOT EXISTS app.users (
                                         id             BIGSERIAL PRIMARY KEY,
                                         public_id      UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id      BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    identity_id    BIGINT      REFERENCES app.identities(id) ON DELETE SET NULL,
    email          TEXT,
    full_name      TEXT,
    job_title      TEXT,
    department     TEXT,
    manager_id     BIGINT      REFERENCES app.users(id) ON DELETE SET NULL,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    last_login_at  TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version        BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_users_identity_or_email CHECK (identity_id IS NOT NULL OR email IS NOT NULL),
    CONSTRAINT ck_users_email_format
    CHECK (email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
    );

CREATE INDEX IF NOT EXISTS idx_users_client ON app.users(client_id);
CREATE INDEX IF NOT EXISTS idx_users_identity ON app.users(identity_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON app.users(lower(email));
CREATE INDEX IF NOT EXISTS idx_users_manager ON app.users(manager_id);
CREATE INDEX IF NOT EXISTS idx_users_client_active ON app.users(client_id, is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_users_manager_active ON app.users(manager_id) WHERE is_active;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_client_email_lower
    ON app.users(client_id, lower(email)) WHERE email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_client_identity
    ON app.users(client_id, identity_id) WHERE identity_id IS NOT NULL;

COMMENT ON TABLE app.users IS 'Users within client organizations';
COMMENT ON COLUMN app.users.manager_id IS 'Direct manager for hierarchical reporting';

-- Apply foreign key for owner_user_id after both tables exist
ALTER TABLE app.clients
ADD CONSTRAINT fk_clients_owner_user
FOREIGN KEY (owner_user_id)
REFERENCES app.users(id);


CREATE TABLE IF NOT EXISTS app.roles (
                                         id           BIGSERIAL PRIMARY KEY,
                                         public_id    UUID                NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id    BIGINT              NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    name         TEXT                NOT NULL,
    role_type    VARCHAR  NOT NULL DEFAULT 'TRAINING',
    description  TEXT,
    is_active    BOOLEAN             NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version      BIGINT              NOT NULL DEFAULT 0,

    CONSTRAINT uq_roles_client_name UNIQUE (client_id, name)
    );

CREATE INDEX IF NOT EXISTS idx_roles_client ON app.roles(client_id);
CREATE INDEX IF NOT EXISTS idx_roles_type ON app.roles(role_type);
CREATE INDEX IF NOT EXISTS idx_roles_active ON app.roles(client_id, is_active) WHERE is_active;

COMMENT ON TABLE app.roles IS 'Roles for both admin and training purposes';

CREATE TABLE IF NOT EXISTS app.permissions (
       permission   TEXT PRIMARY KEY,
       display_name TEXT NOT NULL,
       description  TEXT NOT NULL,
       created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp()
    );

COMMENT ON TABLE app.permissions IS 'Catalog of available system permissions';

CREATE TABLE IF NOT EXISTS app.role_permissions (
                                                    role_id     BIGINT NOT NULL REFERENCES app.roles(id) ON DELETE CASCADE,
    permission  TEXT   NOT NULL REFERENCES app.permissions(permission) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission)
    );

CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON app.role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_perm ON app.role_permissions(permission);

COMMENT ON TABLE app.role_permissions IS 'Maps roles to permissions';

CREATE TABLE IF NOT EXISTS app.user_roles (
                                              id          BIGSERIAL PRIMARY KEY,
                                              public_id   UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    user_id     BIGINT      NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    role_id     BIGINT      NOT NULL REFERENCES app.roles(id) ON DELETE CASCADE,
    client_id   BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    assigned_by BIGINT      REFERENCES app.users(id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version     BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT uq_user_roles UNIQUE (user_id, role_id, client_id)
    );

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON app.user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON app.user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_client ON app.user_roles(client_id);

COMMENT ON TABLE app.user_roles IS 'Assigns roles to users';

-- =====================================================
-- UI Settings
-- =====================================================

-- =====================================================
-- UI Settings - Corrected DDL for BaseEntity Inheritance
-- =====================================================

CREATE TABLE IF NOT EXISTS app.default_ui_settings (
    id             BIGSERIAL PRIMARY KEY,
    public_id      UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(), -- ADDED for BaseEntity
    setting_key    TEXT        NOT NULL UNIQUE,
    value          TEXT,
    description    TEXT,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version        BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT ck_default_ui_key_not_blank CHECK (length(btrim(setting_key)) > 0)
    );

COMMENT ON TABLE app.default_ui_settings IS 'Catalog of UI settings with system defaults (Extends BaseEntity)';


CREATE TABLE IF NOT EXISTS app.client_ui_settings (
                                                      id          BIGSERIAL PRIMARY KEY,
                                                      public_id   UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    client_id   BIGINT      NOT NULL REFERENCES app.clients(id) ON DELETE CASCADE,
    setting_key TEXT        NOT NULL REFERENCES app.default_ui_settings(setting_key)
                                                                ON UPDATE CASCADE ON DELETE RESTRICT,
    value       TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version     BIGINT      NOT NULL DEFAULT 0,

    CONSTRAINT uq_client_ui_settings UNIQUE (client_id, setting_key)
    );

CREATE INDEX IF NOT EXISTS idx_client_ui_client_key
    ON app.client_ui_settings(client_id, setting_key) WHERE is_active;

COMMENT ON TABLE app.client_ui_settings IS 'Client-specific UI setting overrides';

-- =====================================================
-- Authentication Events (Audit Log)
-- =====================================================

CREATE TABLE IF NOT EXISTS app.audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    public_id   UUID        NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    client_id   BIGINT      REFERENCES app.clients(id) ON DELETE SET NULL,
    user_id     BIGINT      REFERENCES app.users(id) ON DELETE SET NULL,
    provider_id BIGINT      REFERENCES app.identity_providers(id) ON DELETE SET NULL,
    event_type  TEXT        NOT NULL,
    ip          INET,
    user_agent  TEXT,
    details     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    version     BIGINT      NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_occurred ON app.audit_logs(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_client ON app.audit_logs(client_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON app.audit_logs(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_type ON app.audit_logs(event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_details_gin ON app.audit_logs USING GIN(details);

COMMENT ON TABLE app.audit_logs IS 'Audit log of events';

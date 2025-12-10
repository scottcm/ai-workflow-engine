-- =========================================================
-- Seed Data for Test Schema
-- =========================================================

-- Tenants
INSERT INTO app.tenants (public_id, code, name)
VALUES
  (gen_random_uuid(), 'tenant_alpha', 'Tenant Alpha'),
  (gen_random_uuid(), 'tenant_beta',  'Tenant Beta');

-- Tiers (global)
INSERT INTO global.tiers (public_id, code, name, description)
VALUES
  (gen_random_uuid(), 'FREE',  'Free Tier',  'Basic global tier for testing'),
  (gen_random_uuid(), 'PRO',   'Pro Tier',   'Pro tier with additional features'),
  (gen_random_uuid(), 'ENTER', 'Enterprise', 'Enterprise tier with full features');

-- Products per tenant x tier
INSERT INTO app.products (public_id, tenant_id, tier_id, sku, name, description, price)
SELECT
    gen_random_uuid()                                          AS public_id,
    t.id                                                       AS tenant_id,
    tier.id                                                    AS tier_id,
    'SKU-' || t.code || '-' || tier.code                       AS sku,
    t.name || ' Product (' || tier

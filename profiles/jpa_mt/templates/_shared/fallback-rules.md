## Fallback Rules

When standards bundle does not define a behavior, apply these defaults:

1. **Repository Base Interface**
   - Default: `JpaRepository<Entity, Long>`

2. **Timestamp Types**
   - `TIMESTAMPTZ` → `OffsetDateTime`
   - `TIMESTAMP` → `LocalDateTime` (if no timezone)

3. **Multi-Tenancy Classification**
   - Has tenant_id/client_id/org_id column → Tenant-scoped
   - Is the tenant/client/org table itself → Tenant entity
   - No tenant column → Global/Shared

4. **Relationship Modeling**
   - Model FK if related entity file is attached
   - Skip FK if related entity not provided

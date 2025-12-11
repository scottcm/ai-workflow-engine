# Architecture and Multitenancy (AI-Optimized)
<!--
tags: [architecture, multitenancy, transactions, rls, admin-pool, tenant-pool, service-layer]
ai-profile: [domain, vertical, service, code-review]
-->

## Tenant Model Requirements
- **`tenant_id` is the canonical tenant identifier.**
- Table: `app.tenants`
  - Column: `tenant_id`
- `tenant_id` MUST appear first in multi-tenant API method signatures where applicable:
  - `(UUID tenantId, UUID id, …)`
  - `(UUID tenantId, UUID resourceId, …)` when it enhances clarity.

---

## Connection Pool Requirements

### Admin / Provisioning Repositories
- MUST use the **Admin Connection Pool**.
- Admin connections **bypass RLS**.
- MAY ONLY be used for:
  - tenant creation
  - provisioning tasks
  - administrative metadata
- MUST NOT be used for tenant-scoped runtime operations.

### Tenant Runtime Repositories
- MUST use the **Tenant Connection Pool**.
- RLS MUST be **enabled and enforced** via:
  ```
  SET LOCAL app.current_tenant_id = :tenantId
  ```
- All API-serving business logic MUST run in the tenant pool context.
- A single method MUST NOT mix admin-pool and tenant-pool operations.
  - If both are required, they MUST be split into separate service-layer methods.

---

## Transaction Requirements
- Transactions MUST be declared **only** in the Service Layer.
- Controllers and repositories MUST NOT declare transactional boundaries.
- Tenant-scoped operations:
  - MUST use `@Transactional` with the **tenant pool**.
  - MUST NOT disable or bypass RLS.
- Admin/provisioning operations:
  - MUST use `@AdminTransactional`.
  - SHOULD use `REQUIRES_NEW` when it prevents tenant/tenant pool mixing.
- Long-running operations MUST use batching/pagination.
- Transactions MUST NOT be used to circumvent RLS protections.

---

## API Signature & Naming Requirements
- Because **tenant_id is the canonical tenant identifier**, method signatures MUST reflect consistent ordering:
  - `(UUID tenantId, UUID id, …)`
  - `(UUID tenantId, UUID resourceId, …)`
- Method verbs MUST be consistent across the codebase:
  - `createX`, `updateX`, `deleteX`, `getX`, `listX`

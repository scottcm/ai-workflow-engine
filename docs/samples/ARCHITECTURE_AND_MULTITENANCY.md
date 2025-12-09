# Architecture And Multitenancy (AI-Optimized)
<!--
tags: [architecture, multitenancy, transactions, rls, admin-pool, tenant-pool, service-layer]
ai-profile: [domain, vertical, service, code-review]
-->

> This document defines **Control Plane multi-tenancy**, connection pools, and transaction rules.  
> **IMPORTANT:** In this system, the *multi-tenant identifier is called `client_id`*,  
> even though it represents the **tenant**.  
> The database table is named **`app.clients`**, and its key column is **`client_id`**.  
> AI MUST treat **client = tenant** everywhere in this architecture.

### Requirements (Tenant Model)
- The Control Plane **IS a multi-tenant architecture**, even though the schema uses the term *client*.
    - **`client_id` is the tenant identifier.**
    - Table: `app.clients`  
      Column: `client_id`  
      → These MUST be interpreted as the **tenant** for all RLS and isolation logic.

### Requirements (Connection Pools)
- **Admin / Provisioning Repositories**
    - MUST use the **Admin Connection Pool**.
    - Admin connections **bypass RLS**.
    - MAY ONLY be used for:
        - tenant/client creation
        - provisioning tasks
        - administrative metadata
    - MUST NOT be used for tenant-scoped runtime operations.

- **Tenant Runtime Repositories**
    - MUST use the **Tenant Connection Pool**.
    - RLS MUST be **enabled and enforced** through `SET LOCAL app.current_client_id = :clientId`.
    - All business logic serving API requests MUST run in this context.

- A single method MUST NOT mix admin-pool and tenant-pool work.
    - If both are required, they MUST be split into separate service-layer methods.

### Requirements
- Transaction boundaries MUST exist only in the **Service layer**, never in controllers or repositories.
- Tenant-scoped operations:
    - MUST use `@Transactional` with the tenant pool.
    - MUST NOT disable or bypass RLS.
- Admin/provisioning operations:
    - MUST use `@AdminTransactional`.
    - SHOULD use `REQUIRES_NEW` where it prevents tenant-pool interaction.

- Long-running tasks MUST be chunked (pagination/batching).
- Transactions MUST NOT be used to work around RLS enforcement.

### Requirements
- Because **client_id = tenant_id**, API signatures MUST reflect this consistent ordering:
    - `(UUID clientId, UUID id, …)`
    - or when naming clarity matters: `(UUID tenantId, UUID resourceId, …)`
- Method verbs MUST be consistent across the codebase:
    - `createX`, `updateX`, `deleteX`, `getX`, `listX`

# Jpa And Database (AI-Optimized)
> Canonical rules for how entities, IDs, relationships, JSONB, timestamps, and query patterns MUST be implemented.  
> These requirements are optimized for correctness, RLS compatibility, and predictable AI generation.

### Requirements: Entity Identity, Schema, and Naming

- Entities MUST explicitly declare schema and table:
  - `@Table(schema = "<schema>", name = "<table>")`
- Entities MUST NOT rely on default schema resolution.
- Entity names MUST remain singular and MUST match the conceptual domain entity.
- Primary keys SHOULD use `Long` or `UUID` per canonical schema definition.

**Examples from this codebase:**
- `@Table(schema = "app", name = "tenants")` → `Tenant.java`
- `@Table(schema = "app", name = "products")` → `Product.java`
- `@Table(schema = "global", name = "tiers")` → `Tier.java`

### Requirements: Timestamps

- All persisted timestamps MUST use:
  - `java.time.OffsetDateTime`
- The following MUST NOT be used for persisted timestamps:
  - `LocalDateTime`
  - `java.util.Date`
  - `java.sql.Timestamp`

**Example:**
```java
@Column(name = "created_at", nullable = false, updatable = false)
private OffsetDateTime createdAt;

@Column(name = "updated_at", nullable = false)
private OffsetDateTime updatedAt;
```

### Requirements: Relationships

- Foreign-key relationships:
  - MUST use `@ManyToOne(fetch = FetchType.LAZY)` by default.
  - EAGER fetching is FORBIDDEN unless explicitly justified in an ADR or docstring.
- Raw FK primitive fields MUST NOT coexist with object relationships **unless all are true**:
  - Performance or DTO mapping requires it.
  - Field is marked `insertable = false, updatable = false`.
  - The intent is documented in a comment or ADR.

**Examples from this codebase:**

Product → Tenant (tenant-scoped relationship):
```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "tenant_id", nullable = false)
private Tenant tenant;
```

Product → Tier (cross-schema relationship to global entity):
```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "tier_id")
private Tier tier;  // import com.example.global.domain.tier.Tier
```

### Requirements: JSON / JSONB

- PostgreSQL `jsonb` MUST be mapped using a supported JSON type (e.g., via hypersistence-utils JSON types).
- JSON payloads SHOULD be represented as typed value objects (records/POJOs), not generic maps, when the shape is known and stable.

### Requirements: Query Patterns & Performance

- Simple queries SHOULD use Spring Data method-name queries.
- Complex queries MAY use `@Query` (JPQL or native).
- Dynamic filtering MAY use Specifications **only if standardized** in a separate document.
- Queries that may return large result sets MUST use:
  - Pagination (`Pageable`), or
  - Explicit SQL limits.
- N+1 issues MUST be prevented using one or more of:
  - `JOIN FETCH`
  - `@EntityGraph`
  - Projection-based queries

### Requirements: Multi-Tenancy & Repository Query Rules

The system supports both tenant-scoped and global entities. Repositories MUST respect multi-tenancy rules to remain compatible with Row-Level Security (RLS) and admin/tenant connection pools.

**Entity Classification in This Codebase:**

| Entity | Schema | Classification | Has tenant_id? |
|--------|--------|----------------|----------------|
| `Tenant` | `app` | Tenant entity | No (IS the tenant) |
| `Product` | `app` | Tenant-scoped | Yes |
| `Tier` | `global` | Global/shared | No |

**Classification Rules**

- An entity is considered **tenant-scoped** when:
  - Its underlying table contains a tenant identifier column (e.g., `tenant_id`), **and**
  - The table is intended to be isolated per tenant.
- An entity is considered **global/shared** when:
  - Its table does NOT contain a tenant identifier column, or
  - It is explicitly designated as global (e.g., lookup/reference data).
- An entity is considered a **tenant/organization entity** when:
  - It represents the tenant itself (e.g., `app.tenants`), and
  - Its records are not scoped by a higher-level tenant identifier.

**General Rules**

- Tenant isolation MUST be enforced by the database via RLS where configured.
- Repository methods MUST NOT attempt to bypass RLS (for example, by using a connection/pool that is not subject to tenant policies, unless explicitly documented as an admin-only operation).
- Repository code MUST assume:
  - Tenant-scoped operations run on a tenant pool with RLS enabled.
  - Cross-tenant operations (if any) are performed via a separate admin context and MUST be explicitly justified in architecture documentation.

**Tenant-Scoped Repositories**

For entities whose tables are tenant-scoped (e.g., `Product`):

- Repository methods MUST NOT accept an explicit tenant identifier parameter **unless**:
  - The architecture explicitly requires it, and
  - The planned repository design calls it out.
- When writing custom `@Query` methods:
  - The query MUST NOT introduce conditions that conflict with RLS semantics.
  - The query MUST NOT filter by a tenant identifier different from the current tenant context.
- All "find by business key" methods MUST uniquely identify records within a tenant's data.

**Example - ProductRepository:**
```java
// CORRECT: RLS handles tenant filtering
Optional<Product> findBySku(String sku);

// WRONG: Do not pass tenant_id explicitly
Optional<Product> findBySkuAndTenantId(String sku, Long tenantId);
```

**Global / Shared Repositories**

For entities whose tables are global/shared (e.g., `Tier`):

- Repository methods MUST NOT introduce artificial tenant filters.
- Queries SHOULD use natural/business keys or primary keys as defined in the schema and planning document.
- When global entities participate in relationships with tenant-scoped entities:
  - Mappings MUST respect the direction and cardinality specified in the planning document.
  - Repositories MUST NOT create cross-tenant visibility by joining global and tenant-scoped tables in ways that defeat RLS.

**Example - TierRepository:**
```java
// CORRECT: Global lookup by business key
Optional<Tier> findByCode(String code);

// CORRECT: Global lookup by public ID
Optional<Tier> findByPublicId(UUID publicId);
```

**Tenant / Organization Entity Repositories**

For the entity that represents the tenant/organization itself (e.g., `Tenant`):

- Repositories MAY expose methods to:
  - Look up a tenant by its primary key.
  - Look up a tenant by business identifier (e.g., `code`).
- These repositories are **not** tenant-scoped; they operate at the platform level and MUST be used carefully in admin contexts only.

**Example - TenantRepository:**
```java
Optional<Tenant> findByCode(String code);
Optional<Tenant> findByPublicId(UUID publicId);
```

**AI Generation Rules**

When generating repositories:

- The generator MUST:
  - Classify the entity as tenant-scoped vs global vs tenant-entity based on the schema and planning document.
  - Follow the above rules and MUST NOT invent tenant parameters or cross-tenant behavior.
- Where the planning document defines specific repository methods, the generator MUST:
  - Implement those methods exactly.
  - Avoid introducing additional finder methods, especially those that rely on unplanned tenant identifiers.
  
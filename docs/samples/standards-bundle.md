--- ORG.md ---

### Requirements
- Classes MUST use `UpperCamelCase`.
- Interfaces MUST use `UpperCamelCase` and MUST NOT use an `I` prefix.
- Methods MUST use `lowerCamelCase`.
- Variables (fields & locals) MUST use `lowerCamelCase`.
- Constants MUST use `ALL_CAPS_WITH_UNDERSCORES`.
- Packages MUST use `all.lowercase.with.dots`.

### Requirements
- Persistent entity class names SHOULD be the **singular UpperCamelCase** form of the conceptual entity.  
  Example: `identity_providers` → `IdentityProvider`.
- Entities MUST avoid suffixes such as `Entity`, `Model`, `Record`, `DO`, etc.

### Requirements
- Indentation MUST be 4 spaces.
- Braces MUST follow K&R / 1TBS.
- Imports MUST follow standard grouping (Static → Java → 3rd Party → App).
- `System.out` and `printStackTrace` MUST NOT appear in generated code.

### Requirements
- SLF4J MUST be used for all logging.
- `System.out.println` is forbidden.
- Logger declaration SHOULD follow:  
  `private static final Logger log = LoggerFactory.getLogger(CurrentClass.class);`
- Correct log levels MUST be used: DEBUG (diagnostic), INFO (ops), WARN (recoverable), ERROR (failure).

### Requirements
- Prefer unchecked (`RuntimeException`) over checked exceptions.
- Checked exceptions MUST NOT be added without justification.
- Methods MUST NOT throw generic `Exception`.
- Catch blocks MUST NOT swallow exceptions.
- Wrapped exceptions MUST preserve the cause.

### Requirements
- Constructor injection MUST be used for all dependencies.
- Field injection (`@Autowired`) is forbidden.
- Lombok `@RequiredArgsConstructor` SHOULD be used.
- Circular dependencies MUST be avoided.

### Requirements
- **Testing:** JUnit 5 and AssertJ MUST be used.
- **Lombok:** Permitted and encouraged for boilerplate elimination.
- **Logging:** SLF4J is the only allowed logging façade.

### Requirements
- Classes SHOULD have a single clear responsibility (SRP).
- Large procedural blocks MUST be refactored into helper methods.
- Public APIs MUST remain stable; internals MUST be private or package-private.
- Immutability SHOULD be preferred when practical.

--- PACKAGES_AND_LAYERS.md ---

### Requirements
- The Control Plane MUST follow the canonical directory structure under  
  `com.example.app`:

```text
com.example.app/
├── api/
│   ├── controller/
│   └── dto/
│       ├── tenant/
│       ├── provisioning/
│       └── tenant/
├── domain/
│   ├── access/
│   ├── audit/
│   ├── catalog/
│   ├── tenant/
│   ├── identity/
│   ├── provisioning/
│   ├── settings/
│   └── user/
├── exception/
├── mapper/
├── service/
│   ├── access/
│   ├── audit/
│   ├── catalog/
│   ├── tenant/
│   ├── identity/
│   ├── provisioning/
│   └── settings/
├── tx/
└── support/
```

- **Domain**, **Service**, **API**, **Mapper**, **Exception**, **Transaction**, and **Support** layers MUST remain separate and MUST NOT be reorganized arbitrarily.
- Bounded-context packages (e.g., `tenant`, `provisioning`, `access`, `audit`, `catalog`, `identity`, `settings`, `user`) MUST appear under both `domain` and `service` when that context has behavior.
- All AI-generated classes MUST respect this structure.

### Requirements
- MUST contain JPA entities and Spring Data repositories for its bounded context.
- Entity and its repository MUST share the **same package**.
- MUST NOT contain `entity/` or `repository/` subpackages.
- Enums and value objects MUST live alongside their entity.

### Requirements
- MUST contain business logic for each bounded context.
- SHOULD define one primary service per main aggregate/entity.
- Complex workflows MAY have additional dedicated services.

### Requirements
- Controllers MUST live under `api.controller`, in a **flat** structure.
- External DTOs MUST live under `api.dto.<bounded_context>` (e.g., `api.dto.tenant`, `api.dto.provisioning`, `api.dto.tenant`).
- DTOs MUST follow naming conventions (`*Request`, `*Response`).

### Requirements
- Mapper package MUST remain flat (NO subdirectories).
- MUST define exactly one mapper per entity.
- Controllers and services MUST NOT embed mapping logic.

### Requirements
- MUST contain domain exceptions for Control Plane concerns.
- MUST include global API exception translation where applicable.

### Requirements
- MUST contain RLS logic, transaction-scoped annotations, and aspects.
- MUST NOT contain ANY business logic.

### Requirements
- MUST contain simple utility/support classes only.
- MUST NOT contain domain logic or cross-bounded-context behavior.

### Requirements
- Domain logic MUST exist ONLY within domain and service layers.
- Controllers MUST NOT call repositories directly; they MUST call services.
- Controllers MUST remain thin (validation + delegation only).
- Package placement MUST follow established conventions with NO deviations unless approved by ADR.

### Requirements
- Each bounded context MUST include:
    - Domain entities + repositories under `domain.<bounded_context>`
    - Service logic under `service.<bounded_context>`
    - API DTOs under `api.dto.<bounded_context>` when exposed externally
    - A related mapper in the shared `mapper` package
- Current bounded contexts include (but are not limited to):
    - `access`, `audit`, `catalog`, `tenant`, `identity`, `provisioning`, `settings`, `user`.
- New bounded contexts MUST follow this same structure.

--- JPA_AND_DATABASE.md ---

### Requirements: Entity Identity, Schema, and Naming

- Entities MUST explicitly declare schema and table:
  - `@Table(schema = "<schema>", name = "<table>")`
- Entities MUST NOT rely on default schema resolution.
- Entity names MUST remain singular and MUST match the conceptual domain entity.
- Primary keys SHOULD use `Long` or `UUID` per canonical schema definition.

### Requirements: Timestamps

- All persisted timestamps MUST use:
  - `java.time.OffsetDateTime`
- The following MUST NOT be used for persisted timestamps:
  - `LocalDateTime`
  - `java.util.Date`
  - `java.sql.Timestamp`

### Requirements: Relationships

- Foreign-key relationships:
  - MUST use `@ManyToOne(fetch = FetchType.LAZY)` by default.
  - EAGER fetching is FORBIDDEN unless explicitly justified in an ADR or docstring.
- Raw FK primitive fields MUST NOT coexist with object relationships **unless all are true**:
  - Performance or DTO mapping requires it.
  - Field is marked `insertable = false, updatable = false`.
  - The intent is documented in a comment or ADR.

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

**Classification**

- An entity is considered **tenant-scoped** when:
  - Its underlying table contains a tenant identifier column (for example: `tenant_id`, `client_id`, or `org_id`), **and**
  - The table is intended to be isolated per tenant.
- An entity is considered **global/shared** when:
  - Its table does NOT contain a tenant identifier column, or
  - It is explicitly designated as global (e.g., lookup/reference data).
- An entity is considered a **tenant/organization entity** when:
  - It represents the tenant itself (e.g., a `Tenant` table in a dedicated schema), and
  - Its records are not scoped by a higher-level tenant identifier.

**General Rules**

- Tenant isolation MUST be enforced by the database via RLS where configured.
- Repository methods MUST NOT attempt to bypass RLS (for example, by using a connection/pool that is not subject to tenant policies, unless explicitly documented as an admin-only operation).
- Repository code MUST assume:
  - Tenant-scoped operations run on a tenant pool with RLS enabled.
  - Cross-tenant operations (if any) are performed via a separate admin context and MUST be explicitly justified in architecture documentation.

**Tenant-Scoped Repositories**

For entities whose tables are tenant-scoped:

- Repository methods MUST NOT accept an explicit tenant identifier parameter **unless**:
  - The architecture explicitly requires it, and
  - The planned repository design calls it out.
- When writing custom `@Query` methods:
  - The query MUST NOT introduce conditions that conflict with RLS semantics.
  - The query MUST NOT filter by a tenant identifier different from the current tenant context.
- All “find by business key” methods MUST uniquely identify records within a tenant’s data.  
  Example: `findByCode(String code)` is acceptable only if `code` is unique per tenant or globally; otherwise, the planning document MUST define the correct method signature.

**Global / Shared Repositories**

For entities whose tables are global/shared:

- Repository methods MUST NOT introduce artificial tenant filters.
- Queries SHOULD use natural/business keys or primary keys as defined in the schema and planning document.
- When global entities participate in relationships with tenant-scoped entities:
  - Mappings MUST respect the direction and cardinality specified in the planning document.
  - Repositories MUST NOT create cross-tenant visibility by joining global and tenant-scoped tables in ways that defeat RLS.

**Tenant / Organization Entity Repositories**

For the entity that represents the tenant/organization itself:

- Repositories MAY expose methods to:
  - Look up a tenant by its primary key.
  - Look up a tenant by business identifier (e.g., `code`, `slug`, or `domain`).
- These repositories are **not** tenant-scoped; they operate at the platform level and MUST be used carefully in admin contexts only.

**AI Generation Rules**

When generating repositories:

- The generator MUST:
  - Classify the entity as tenant-scoped vs global vs tenant-entity based on the schema and planning document.
  - Follow the above rules and MUST NOT invent tenant parameters or cross-tenant behavior.
- Where the planning document defines specific repository methods, the generator MUST:
  - Implement those methods exactly.
  - Avoid introducing additional finder methods, especially those that rely on unplanned tenant identifiers.

  --- ARCHITECTURE_AND_MULTITENANCY.md ---

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

  --- NAMING_AND_API.md ---

  ### Requirements
- **Entities**
    - MUST match the **singular table name** exactly.
    - MUST NOT use suffixes such as `Entity`, `Model`, `Record`, `DO`, etc.
- **Repositories**
    - MUST use the `Repository` suffix.
- **Services**
    - MUST use the `Service` suffix.
- **Tests**
    - MUST use the `Test` suffix and map 1:1 to the class under test.

### Requirements
- **Controllers**
    - MUST use the `*Controller` suffix.
    - MUST remain thin—validation, parameter extraction, delegation only.
- **External API DTOs**
    - MUST use `*Request` and `*Response`.
    - MUST live under `…api.dto.<bounded_context>`.
    - SHOULD use Java **records** when appropriate.
- **Internal-only DTOs**
    - MAY use `*Dto`.
    - MUST NOT be part of external API surfaces.

### Requirements
- All entity↔DTO mapping MUST be performed in `*Mapper` classes.
- Mappers SHOULD live in a dedicated mapper package.
- Services & controllers MUST NOT contain inline/ad-hoc mapping logic.

### Requirements
- Domain exceptions MUST end with `Exception`.
- API exceptions SHOULD be translated via a global `@ControllerAdvice`.

--- BOILERPLATE_AND_DI.md ---

### Requirements
- Lombok **is allowed and encouraged** to eliminate boilerplate.
- Allowed Lombok patterns:
    - `@Data` for simple immutable structures or DTO-like classes.
    - `@Builder` for complex construction and readability.
    - `@RequiredArgsConstructor` for constructor injection.
- Lombok usage MUST be **consistent** across the codebase.
- Lombok MUST NOT hide domain logic—use only for boilerplate, not behavior.

### Requirements
- **Constructor Injection ONLY**
    - All Spring components (services, controllers, mappers, etc.) MUST use constructor injection.
    - `@RequiredArgsConstructor` is preferred for brevity and clarity.
- **Field Injection is forbidden**
    - `@Autowired` MUST NOT appear on fields.
    - Constructor-level `@Autowired` MAY be omitted when using `@RequiredArgsConstructor`.
- Injection MUST NOT be performed using setter methods.
- Components MUST depend only on required collaborators; avoid “kitchen sink” injection.

--- 
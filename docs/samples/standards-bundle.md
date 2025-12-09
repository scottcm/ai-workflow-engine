# AI Standards Bundle — Profile: domain

> **Auto-generated. Do not edit directly.**
> Generated from modular standards files.
>
> Source files:
> - JAVA_STANDARDS_ARCHITECTURE_AND_MULTITENANCY.md
> - JAVA_STANDARDS_BOILERPLATE_AND_DI.md
> - JAVA_STANDARDS_JPA_AND_DATABASE.md
> - JAVA_STANDARDS_NAMING_AND_API.md
> - JAVA_STANDARDS_ORG.md
> - JAVA_STANDARDS_PACKAGES_AND_LAYERS.md
>
> Mode: critical

---

## From JAVA_STANDARDS_ARCHITECTURE_AND_MULTITENANCY.md

## 3. Architecture & Security (Multi-Tenancy, Connections, Transactions)

### 3.1 Multi-Tenancy & Connection Pools

- The Control Plane is a **multi-tenant SaaS** system; all data access MUST respect tenant isolation.
- **Admin / Provisioning Repositories**
    - Repositories used for provisioning and administrative tasks (e.g., client creation, schema provisioning) MUST use the **Admin Connection Pool**.
    - Admin pool connections **bypass RLS** and MUST be restricted to provisioning/administrative concerns only.
- **Runtime / Tenant Repositories**
    - Standard application repositories used for normal request handling MUST use the **Tenant Connection Pool**.
    - Tenant pool connections MUST have RLS **enabled and enforced**.
- Admin and tenant operations MUST NOT be mixed in the same method.
    - If both are needed, they MUST be separated into *distinct* methods/services.

### 3.2 Transaction Management

- `@Transactional` MUST be applied **only on Service-layer methods**.
- Repositories MUST remain non-transactional.
- Controllers MUST NOT carry transaction boundaries.
- Default transaction rules:
    - Tenant-scoped operations → `@Transactional` (tenant pool)
    - Admin/provisioning operations → `@AdminTransactional` (admin pool, often `REQUIRES_NEW`)
- Long-running operations MUST be broken into smaller units (pagination, chunking).
- Transactions MUST NOT be used to override RLS boundaries.

### 3.3 API Signatures & Parameter Order

- Tenant/client identifiers SHOULD follow a **consistent parameter order**, e.g.:
    - `(UUID clientId, UUID id, …)`
    - `(UUID tenantId, UUID resourceId, …)`
- Service & controller method verbs MUST be consistent:
    - `createX`, `updateX`, `deleteX`, `getX`, `listX`

---

## From JAVA_STANDARDS_BOILERPLATE_AND_DI.md

## 6. Boilerplate, Lombok, and Dependency Injection

### 6.1 Lombok Usage

- Lombok is **allowed and encouraged** to reduce boilerplate.
- Common patterns:
    - `@Data` for simple entities/DTOs.
    - `@Builder` for complex construction.
    - `@RequiredArgsConstructor` for constructor injection.
- Lombok usage SHOULD remain consistent across the codebase.

### 6.2 Dependency Injection

- **Constructor injection only**:
    - All Spring components (services, controllers, etc.) MUST use constructor injection.
    - Lombok `@RequiredArgsConstructor` is preferred for brevity.
- Field injection is **forbidden**:
    - `@Autowired` on fields MUST NOT be used.
    - `@Autowired` on constructors MAY be omitted when using `@RequiredArgsConstructor`.

### Example (Good)

```java
@Service
@RequiredArgsConstructor
public class ProvisioningService {

    private final ClientRepository clientRepository;
    private final ClientTierRepository clientTierRepository;

    public ClientResponse provisionClient(CreateClientRequest request) {
        // ...
    }
}
```

### Example (Bad)

```java
@Service
public class ProvisioningService {

    @Autowired
    private ClientRepo clientRepo;              // ❌ field injection + wrong naming

    public void provision(CreateClientRequest request) {
        // ...
    }
}
```

---

## From JAVA_STANDARDS_JPA_AND_DATABASE.md

## 4. JPA & Database Standards

### 4.1 Entity Schema & Table Mapping

- All entities MUST specify the schema explicitly:
    - `@Table(schema = "app", name = "<table>")`
- Entities MUST NOT rely on default schema resolution.

### 4.2 IDs & Timestamps

### Requirements
- Primary keys SHOULD use `Long` or `UUID` per canonical schema definition.
- All persisted timestamps MUST use:
    - `java.time.OffsetDateTime`
- The following MUST NOT be used for persisted timestamps:
    - `LocalDateTime`
    - `java.util.Date`
    - `java.sql.Timestamp`

### Requirements (Base Entity)
- All domain entities MUST extend `BaseEntity`.
- `BaseEntity` is a `@MappedSuperclass` that provides common fields:
    - `Long id` - Primary key (BIGINT, auto-generated)
    - `UUID publicId` - External identifier (unique, immutable)
    - `OffsetDateTime createdAt` - Creation timestamp (set by @PrePersist)
    - `OffsetDateTime updatedAt` - Modification timestamp (set by database trigger)
    - `Long version` - Optimistic locking version (managed by JPA)
    - `Boolean isActive` - Soft delete flag (default: true)
- Entities MUST NOT redeclare these inherited fields.
- `publicId` and `createdAt` are set automatically by `@PrePersist` lifecycle callback.
- `updatedAt` is managed by database trigger `app._touch_updated_at` (NOT by JPA).
- `isActive()`, `activate()`, and `deactivate()` methods are available for soft delete.

**Example entity:**
```java
@Entity
@Table(schema = "global", name = "tiers")
@Data
@EqualsAndHashCode(callSuper = true)
public class Tier extends BaseEntity {
    // Do NOT declare: id, publicId, createdAt, updatedAt, version, isActive
    
    @Column(name = "code", nullable = false, unique = true)
    private String code;
    
    @Column(name = "name", nullable = false)
    private String name;
}
```

### 4.3 Relationships & Foreign Keys

- For foreign-key relationships:
    - Use `@ManyToOne(fetch = FetchType.LAZY)` **by default**.
    - EAGER fetching MUST NOT be used unless there is a clear, documented reason.
- Raw FK fields (e.g., `Long clientId`) MUST NOT be duplicated alongside a relationship **unless**:
    - There is a specific performance/DTO-mapping reason, and
    - The field is marked `insertable = false, updatable = false`, and
    - The behavior is documented in a comment and/or ADR.

### 4.4 JSONB Columns

- PostgreSQL `jsonb` columns MUST be mapped using **hypersistence-utils** (e.g., `@Type(JsonType.class)`).
- JSON payloads SHOULD be modeled as value objects (records/POJOs) rather than `Map<String, Object>` where practical.

### 4.5 Query Patterns & Pagination

- Simple queries SHOULD use Spring Data JPA method names.
- More complex queries MAY use `@Query` with JPQL or native SQL as needed.
- Dynamic queries MAY use Specifications or similar patterns if they are standardized for the project.
- Queries that can return large result sets MUST use pagination (`Pageable`) or limit the result size explicitly.
- N+1 issues MUST be avoided using `JOIN FETCH`, `@EntityGraph`, or projections where appropriate.

---

## From JAVA_STANDARDS_NAMING_AND_API.md

## 2. Naming & Packaging (Project-Specific)

These rules are **strict** and exist to keep the codebase predictable for humans and AI.

### 2.1 Core Types

- **Entities**
    - MUST match the **singular table name** exactly.
    - MUST NOT use suffixes like `Entity`, `Model`, `Record`, `DO`, etc.
- **Repositories**
    - MUST use the `Repository` suffix.
- **Services**
    - MUST use the `Service` suffix.
- **Tests**
    - MUST use the `Test` suffix and map 1:1 to the class under test.

### 2.2 API Layer (Controllers & DTOs)

- **Controllers**
    - MUST use the `*Controller` suffix.
    - MUST remain thin: validation, parameter extraction, delegation only.
- **External API DTOs**
    - MUST use `*Request` and `*Response` suffixes.
    - MUST live under `…api.dto.<bounded_context>`.
    - SHOULD use Java **records** when appropriate.
- **Internal-only DTOs**
    - MAY use `*Dto`.
    - MUST NOT be exposed outside internal layers.

### 2.3 Mappers

- Entity↔DTO mapping MUST be centralized in `*Mapper` classes.
- Mappers SHOULD live in a dedicated mapper package.
- Services & controllers MUST NOT contain ad-hoc mapping logic.

### 2.4 Exceptions

- Domain exceptions MUST end with `Exception`.
- API exceptions SHOULD be translated via a global `@ControllerAdvice`.

---

## From JAVA_STANDARDS_ORG.md

## 1.1 General Naming Rules
- **Classes:** MUST use `UpperCamelCase`.
- **Interfaces:** MUST use `UpperCamelCase` and MUST NOT use an `I` prefix.
- **Methods:** MUST use `lowerCamelCase`.
- **Variables (fields & locals):** MUST use `lowerCamelCase`.
- **Constants:** MUST use `ALL_CAPS_WITH_UNDERSCORES`.
- **Packages:** MUST use `all.lowercase.with.dots`.

## 1.2 Entity Naming
- When mapping to persistent storage, **entity class names SHOULD be the singular UpperCamelCase form of the underlying conceptual entity**.
  Example: `identity_providers` → `IdentityProvider`.


### AI Style Summary
> **Context:** The code will be auto-formatted by the IDE. Generate code matching this structure to minimize diffs.

- **Indentation:** 4 spaces (no tabs).
- **Braces:** K&R style (opening brace on same line).
- **Imports:** Standard Java order (Static -> Java -> 3rd Party -> App).
- **Forbidden:** No `System.out`, no `printStackTrace`.


## 3.1 Logging
- **SLF4J MUST be used** as the logging façade.
- **System.out.println is strictly forbidden.**
- Classes SHOULD define a logger as: `private static final Logger log = LoggerFactory.getLogger(CurrentClass.class);`
- Log levels: `DEBUG` (diagnostic), `INFO` (ops), `WARN` (recoverable), `ERROR` (failure).

## 3.2 Exception Handling
- **Prefer unchecked exceptions** (`RuntimeException`).
- **Checked exceptions** MUST NOT be introduced without deliberate justification.
- Methods MUST NOT throw generic `Exception`.
- Catch blocks MUST NOT swallow exceptions silently.
- Wrapping exceptions SHOULD preserve the cause via `new MyException("message", ex)`.

## 3.3 Dependency Injection
- **Constructor Injection MUST be used** for all dependencies.
- **Field Injection (e.g., `@Autowired` on fields) is forbidden.**
- Use Lombok’s `@RequiredArgsConstructor` or manual constructors.
- Circular dependencies MUST be avoided.

## 3.4 Approved Libraries
- **Testing:** JUnit 5 (Jupiter) and AssertJ MUST be used. No JUnit 4.
- **Lombok:** Permitted and encouraged.
- **Logging:** SLF4J only.


# 4. Code Organization & Structure
- **SRP:** Classes should have a single clear responsibility.
- **Small Methods:** Large procedural blocks MUST be refactored into helper methods.
- **Visibility:** Public APIs MUST be stable; internals MUST be package-private or private.
- **Immutability:** SHOULD be preferred where practical.

---

## From JAVA_STANDARDS_PACKAGES_AND_LAYERS.md

## 7. Package & Layering Conventions

These are **project-level structure rules** to keep the codebase and AI-generated code aligned.

### 7.1 Actual Package Structure

```
com.skillsharbor.backend.controlplane/
├── domain/
│   ├── client/
│   ├── tenant/
│   ├── user/
│   └── provisioning/
├── service/
├── api/
│   ├── controller/
│   └── dto/
├── mapper/
├── exception/
├── config/
├── tx/
└── support/
```

### 7.2 Package Rules

**Domain Layer (`…domain.<bounded_context>`)**
- Contains JPA entities and Spring Data repositories for a bounded context.
- Entity and its repository MUST be in the same package.
- NO separate `entity/` or `repository/` subdirectories.
- Enums and value objects belong with their entity.

**Service Layer (`…service.<bounded_context>`)**
- Contains business logic organized by bounded context.
- One primary service per main aggregate/entity.
- Complex workflows MAY have dedicated services.

**API Layer (`…api`)**
- **Controllers** in `api.controller` MUST be flat.
- **DTOs** under `api.dto.<bounded_context>` MUST follow naming conventions.

**Mapper Layer (`…mapper`)**
- Flat structure (NO subdirectories).
- One mapper per entity.

**Exception Layer (`…exception`)**
- Contains domain exceptions + global handler.

**Configuration Layer (`…config`)**
- Spring config, data sources, Hibernate, security.

**Transaction Layer (`…tx`)**
- RLS logic + custom transaction annotations.
- MUST NOT contain business logic.

**Support Layer (`…support`)**
- Utilities only, no domain logic.

### 7.3 Cross-Layer Rules

- Domain logic MUST be in domain/service layers ONLY.
- Controllers MUST NOT call repositories directly; they MUST go through services.
- Controllers MUST remain thin.
- Package placement MUST follow conventions for human + AI consistency.

### 7.4 Bounded Context Organization

Each bounded context MUST contain:
- Domain entities + repositories
- Service logic
- API DTOs
- Mapper in shared mapper package

New bounded contexts MUST follow the same structure.

---

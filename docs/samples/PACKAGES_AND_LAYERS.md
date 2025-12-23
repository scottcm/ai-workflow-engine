# Packages And Layers (AI-Optimized)
> Canonical rules for package structure, bounded contexts, and layering.  
> These rules keep human-written and AI-generated code aligned and predictable, and they MUST match the real package layout.

### Requirements: Schema to Package Mapping

| DB Schema | Java Package Root |
|-----------|-------------------|
| `app`     | `com.example.app.domain` |
| `global`  | `com.example.global.domain` |

- Table name (singular) determines bounded context subdirectory
- Examples:
  - `app.tenants` → `com.example.app.domain.tenant.Tenant`
  - `app.products` → `com.example.app.domain.product.Product`
  - `global.tiers` → `com.example.global.domain.tier.Tier`

### Requirements: App Package Structure

- The application MUST follow this canonical directory structure:

```
com.example.app/
├── api/
│   ├── controller/
│   └── dto/
│       ├── product/
│       └── tenant/
├── domain/
│   ├── product/
│   └── tenant/
├── exception/
├── mapper/
├── service/
│   ├── product/
│   └── tenant/
├── tx/
└── support/
```

### Requirements: Global Package Structure

- Global/shared entities (tables in `global` schema) MUST live under:
  `com.example.global.domain.<bounded_context>`

```
com.example.global/
└── domain/
    └── tier/
```

- When app-schema entities reference global-schema entities:
  - Import the fully-qualified class name
  - Do NOT duplicate global entities into app packages

### Requirements: Layer Separation

- **Domain**, **Service**, **API**, **Mapper**, **Exception**, **Transaction**, and **Support** layers MUST remain separate and MUST NOT be reorganized arbitrarily.
- Bounded-context packages (e.g., `tenant`, `product`) MUST appear under both `domain` and `service` when that context has behavior.
- All AI-generated classes MUST respect this structure.

### Requirements: Domain Layer

- MUST contain JPA entities and Spring Data repositories for its bounded context.
- Entity and its repository MUST share the **same package**.
- MUST NOT contain `entity/` or `repository/` subpackages.
- Enums and value objects MUST live alongside their entity.

### Requirements: Service Layer

- MUST contain business logic for each bounded context.
- SHOULD define one primary service per main aggregate/entity.
- Complex workflows MAY have additional dedicated services.

### Requirements: API Layer

- Controllers MUST live under `api.controller`, in a **flat** structure.
- External DTOs MUST live under `api.dto.<bounded_context>` (e.g., `api.dto.product`, `api.dto.tenant`).
- DTOs MUST follow naming conventions (`*Request`, `*Response`).

### Requirements: Mapper Layer

- Mapper package MUST remain flat (NO subdirectories).
- MUST define exactly one mapper per entity.
- Controllers and services MUST NOT embed mapping logic.

### Requirements: Exception Layer

- MUST contain domain exceptions for application concerns.
- MUST include global API exception translation where applicable.

### Requirements: Transaction Layer (tx)

- MUST contain RLS logic, transaction-scoped annotations, and aspects.
- MUST NOT contain ANY business logic.

### Requirements: Support Layer

- MUST contain simple utility/support classes only.
- MUST NOT contain domain logic or cross-bounded-context behavior.

### Requirements: Architectural Constraints

- Domain logic MUST exist ONLY within domain and service layers.
- Controllers MUST NOT call repositories directly; they MUST call services.
- Controllers MUST remain thin (validation + delegation only).
- Package placement MUST follow established conventions with NO deviations unless approved by ADR.

### Requirements: Bounded Context Completeness

- Each bounded context MUST include:
    - Domain entities + repositories under `domain.<bounded_context>`
    - Service logic under `service.<bounded_context>`
    - API DTOs under `api.dto.<bounded_context>` when exposed externally
    - A related mapper in the shared `mapper` package
- Current bounded contexts:
    - App schema: `tenant`, `product`
    - Global schema: `tier`
- New bounded contexts MUST follow this same structure.

### Requirements: Cross-Schema Relationships

- When an entity in `app` schema references an entity in `global` schema:
  - Use standard `@ManyToOne` relationship
  - Import the global entity using its fully-qualified class name
  - Example: `import com.example.global.domain.tier.Tier;`
  - Global entities are read-only from tenant context
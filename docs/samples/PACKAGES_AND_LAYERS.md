# Packages And Layers (AI-Optimized)
<!--
tags: [packages, layering, architecture, bounded-contexts, structure, api, domain]
ai-profile: [domain, vertical, service, api, code-review, unit, integration, schema]
-->

> Canonical rules for package structure, bounded contexts, and layering within the Control Plane.  
> These rules keep human-written and AI-generated code aligned and predictable, and they MUST match the real package layout.

### Requirements
- The Control Plane MUST follow the canonical directory structure under  
  `com.skillsharbor.backend.controlplane`:

```text
com.skillsharbor.backend.controlplane/
├── api/
│   ├── controller/
│   └── dto/
│       ├── client/
│       ├── provisioning/
│       └── tenant/
├── domain/
│   ├── access/
│   ├── audit/
│   ├── catalog/
│   ├── client/
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
│   ├── client/
│   ├── identity/
│   ├── provisioning/
│   └── settings/
├── tx/
└── support/
```

- **Domain**, **Service**, **API**, **Mapper**, **Exception**, **Transaction**, and **Support** layers MUST remain separate and MUST NOT be reorganized arbitrarily.
- Bounded-context packages (e.g., `client`, `provisioning`, `access`, `audit`, `catalog`, `identity`, `settings`, `user`) MUST appear under both `domain` and `service` when that context has behavior.
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
- External DTOs MUST live under `api.dto.<bounded_context>` (e.g., `api.dto.client`, `api.dto.provisioning`, `api.dto.tenant`).
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
    - `access`, `audit`, `catalog`, `client`, `identity`, `provisioning`, `settings`, `tenant`, `user`.
- New bounded contexts MUST follow this same structure.

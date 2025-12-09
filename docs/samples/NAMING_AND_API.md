# Naming And Api (AI-Optimized)
<!--
tags: [naming, api, controller, dto, mapper, exceptions, packaging]
ai-profile: [domain, vertical, service, api, code-review, unit, integration, schema]
-->

> This document is part of the Control Plane Java standards set.  
> It focuses on naming, controllers, DTOs, mappers, and exceptions.

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

# Boilerplate And Di (AI-Optimized)
<!--
tags: [boilerplate, di, dependency-injection, lombok, constructor-injection, service-layer]
ai-profile: [domain, vertical, service, api, code-review, unit, integration, schema]
-->

> This document defines the canonical rules for boilerplate elimination, Lombok usage,  
> and strict dependency-injection patterns used across the Control Plane.

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

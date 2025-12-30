{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/generation-guidelines.md}}

---

# Vertical Slice Code Generation Request

Generate a complete vertical slice from entity to controller:
1. JPA entity class
2. Spring Data repository interface
3. Service class
4. Controller class
5. Request/Response DTOs
6. Entity-DTO mapper

Implement the planning document exactly. Apply standards, then fallback rules where silent.

---

## Entity Class

- Use `@Table(schema = "...", name = "...")` from DDL
- Declare all non-inherited fields from plan
- Map relationships exactly as planned (use Target Entity FQCN)
- Respect ID, timestamp, versioning rules from standards

## Repository Interface

- Extend appropriate base interface (e.g., `JpaRepository<Entity, Long>`)
- Declare only query methods specified in plan
- Respect tenant behavior from standards

## Service Class

- Implement business operations specified in plan
- Inject repository
- Apply transaction boundaries per standards
- Respect tenant scoping from standards

## Controller Class

- Implement REST endpoints specified in plan
- Use DTOs for request/response
- Apply validation annotations per standards
- Respect API naming conventions from standards

## DTOs

- Create request/response DTOs as specified in plan
- Include only fields needed for each operation
- Apply validation annotations where specified

## Mapper

- Map between entity and DTOs
- Use mapping approach from standards (manual, MapStruct, etc.)

**Do NOT generate:** Components not specified in plan.

---

## Pre-Output Validation

Before emitting bundle, verify:
- All planned artifacts present
- All planned fields and methods implemented
- All relationships mapped with correct imports
- No extra artifacts, fields, or methods introduced

If validation fails, emit single-line error message and no file markers.

{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/generation-guidelines.md}}

---

# Domain Layer Code Generation Request

Generate exactly:
1. One JPA entity class
2. One Spring Data repository interface

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

**Do NOT generate:** DTOs, services, controllers, or methods not in plan.

---

## Pre-Output Validation

Before emitting bundle, verify:
- All planned fields mapped
- All planned relationships implemented (with correct imports)
- All planned repository methods present
- No extra fields or methods introduced

If validation fails, emit single-line error message and no file markers.

---

## Output Destination

Save your complete code bundle as `generation-response.md` to same location as `generation-prompt.md`.
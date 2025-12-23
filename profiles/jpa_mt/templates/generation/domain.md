{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/generation-guidelines.md}}

---

# Domain Layer Code Generation Request

## Context

You are in the **Generation** phase for a single domain entity and its repository.

- Planning phase is complete with an approved `planning-response.md`
- Standards bundle and schema DDL are available as references

Generate exactly:
1. One JPA entity class
2. One Spring Data repository interface

Implement the planning document exactly. Apply standards, then fallback rules where silent.

---

## Required Inputs

- **Planning Document** - Approved `planning-response.md`
- **Standards Bundle** - `standards-bundle.md`
- **Schema DDL** - SQL definition for target table(s)

If any required input is missing or inconsistent, emit validation failure per generation guidelines.

---

## Artifacts to Generate

### Entity Class

- Use `@Table(schema = "...", name = "...")` from DDL
- Declare all non-inherited fields from plan
- Map relationships exactly as planned (use Target Entity FQCN from plan)
- Respect ID, timestamp, versioning rules from standards

### Repository Interface

- Extend appropriate base interface (e.g., `JpaRepository<Entity, Long>`)
- Declare only query methods specified in plan
- Respect tenant behavior from standards

**Do NOT generate:** DTOs, services, controllers, or methods not in plan.

---

## Output Format

Emit exactly two files using bundle format from generation guidelines:

<<<FILE: Tier.java>>>
    package com.example.global.domain.tier;

    import jakarta.persistence.Entity;
    import jakarta.persistence.Table;

    @Entity
    @Table(schema = "global", name = "tiers")
    public class Tier {
        // Fields and mappings from planning document
    }

<<<FILE: TierRepository.java>>>
    package com.example.global.domain.tier;

    import org.springframework.data.jpa.repository.JpaRepository;

    public interface TierRepository extends JpaRepository<Tier, Long> {
        // Methods from planning document
    }

No prose or commentary outside file markers.

---

## Pre-Output Validation

Before emitting bundle, verify:
- All planned fields mapped
- All planned relationships implemented (with correct imports)
- All planned repository methods present
- No extra fields or methods introduced

If validation fails, emit single-line error message and no file markers.
{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/generation-guidelines.md}}

---

# Domain Layer Code Generation Request (Entity + Repository)

## 1. Context

You are in the **Generation** phase for the JPA multi-tenant profile.

- The planning phase has already been completed.
- An approved planning document (e.g., `planning-response.md`) exists for a single domain entity and its repository.
- The standards bundle and schema DDL are available as supporting references.

Your task is to generate:

- Exactly **one JPA entity class**, and
- Exactly **one Spring Data repository interface**,

for the target table and entity described in the planning document.

You MUST implement the design from the planning document exactly, following the standards bundle and applying shared fallback rules only where those sources are silent.

---

## 2. Required Inputs

The following files MUST be available and treated as authoritative:

- **Planning Document**  
  - The most recent approved planning response for this entity and repository  
  - Example: `planning-response.md`
- **Standards Bundle**  
  - Consolidated standards document (e.g., `standards-bundle.md`)
- **Schema DDL**  
  - SQL definition for the target table(s), when provided

If any required input is missing or obviously inconsistent, you MUST follow the validation failure behavior described in the generation phase guidelines and MUST NOT emit any `<<<FILE: ...>>>` markers.

---

## 3. Artifacts to Generate

For the domain scope, you MUST generate:

1. **Entity Class**
   - A JPA entity mapped to the target table described in the planning document.
   - The entity MUST:
     - Use the schema and table names from the DDL (via `@Table(schema = "...", name = "...")`).
     - Declare all non-inherited fields described in the plan and schema.
     - Map relationships (`@ManyToOne`, etc.) exactly as described in the plan.
     - Respect ID, timestamp, and versioning rules from the standards.
     - Use tenant-related types as defined by the schema and standards.

2. **Repository Interface**
   - A Spring Data repository interface for the entity.
   - The repository MUST:
     - Extend the appropriate Spring Data base interface (e.g., `JpaRepository<Entity, IdType>`), as defined by the standards.
     - Declare only the finder/query methods specified in the planning document.
     - Respect any tenant behavior and query rules defined in the standards and planning document.

You MUST NOT:

- Generate additional classes or interfaces (e.g., DTOs, services, controllers).
- Add extra repository methods that are not in the plan.
- Introduce cross-tenant behaviors not defined by the standards.

---

## 4. Domain-Specific Generation Rules

When interpreting the planning document for this domain scope:

- Treat the planning document as the blueprint for:
  - Field names and types
  - Nullability and constraints
  - Relationships and cardinality
  - Repository method signatures and semantics
- Use the schema DDL to:
  - Confirm column types and nullability
  - Confirm primary key and foreign key constraints
- Use the standards bundle and fallback rules to:
  - Determine timestamp types
  - Determine ID types
  - Decide on import style, constructors, accessors, and minimal JavaDoc

If the planning document and schema conflict, you MUST follow the validation failure behavior described in the generation guidelines rather than guessing.

---

## 5. Output Format (Domain Scope Code Bundle)

Your output MUST consist only of a code bundle with exactly two files:

1. The entity class file (e.g., `Tier.java`)
2. The repository interface file (e.g., `TierRepository.java`)

You MUST follow the bundle format defined in the generation phase guidelines:

- One `<<<FILE: ...>>>` marker line per file, using filename only.
- 4-space indentation for all code lines that belong to that file.
- No prose, explanations, or commentary outside the file markers.

Illustrative example (Entity + Repository):

<<<FILE: Tier.java>>>
    package com.aiwf.example.catalog.domain;

    import jakarta.persistence.Entity;
    import jakarta.persistence.Table;

    @Entity
    @Table(schema = "global", name = "tiers")
    public class Tier {
        // Fields and mappings exactly as defined in the planning document
    }

<<<FILE: TierRepository.java>>>
    package com.aiwf.example.catalog.domain;

    import org.springframework.data.jpa.repository.JpaRepository;

    public interface TierRepository extends JpaRepository<Tier, Long> {
        // Repository methods exactly as defined in the planning document
    }

This example is illustrative only.  
Your actual entity and repository MUST reflect the specific design and naming from the planning document and standards.

---

## 6. Validation & Non-Deviation

Before emitting the bundle:

- Verify that:
  - All planned fields are mapped.
  - All planned relationships are implemented.
  - All planned repository methods are present and correctly typed.
- Verify that:
  - No extra fields or methods were introduced.
  - No assumptions were made beyond the planning document, standards bundle, and schema DDL.

If you cannot satisfy these conditions without guessing, you MUST:

- Emit a single-line validation failure message (as defined in the generation guidelines).
- Emit no file markers.

Otherwise, emit exactly the two files in a single bundle and nothing else.

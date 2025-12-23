# Generation Phase Guidelines (JPA MT Profile)

> These guidelines define how the AI must behave during the **code generation phase** for the JPA multi-tenant profile.  
> They are phase-specific and assume that planning has been completed and approved.

---

## 1. Role & Inputs

During the generation phase, the AI acts as:

- An expert Java backend developer with deep knowledge of:
  - Java 21
  - Spring Data JPA
  - Hibernate
  - PostgreSQL
- A strict follower of:
  - The approved planning document (e.g., `planning-response.md`)
  - The standards bundle (organization-wide standards)
  - The database schema DDL

**Required inputs for generation:**

- Approved planning document for the current entity/scope (e.g., `planning-response.md`).
- Standards bundle (e.g., `standards-bundle.md`).
- Relevant schema DDL for the target table(s), when provided.

If any required input is missing, the AI MUST treat this as a validation failure (see Section 5).

**Cross-Schema Entity References:**

If the entity references other entities not in this task:
   - Use the Target Entity FQCN from the approved plan
   - If entity doesn't exist yet, add a TODO comment with the import

---

## 2. Core Responsibilities

During generation, the AI MUST:

- Implement the design described in the approved planning document **exactly**:
  - No additional fields, methods, relationships, or behaviors beyond what the plan defines.
  - All planned fields, relationships, repository methods, and constraints MUST be implemented.
- Follow the standards bundle for:
  - Package naming
  - JPA annotations
  - Timestamp handling
  - Multi-tenancy conventions
  - Repository patterns
- Apply global fallback rules (from `_shared/fallback-rules.md`) **only** when:
  - The standards bundle is silent, and
  - The planning document does not override the behavior.

The AI MUST NOT:

- Change the design intent expressed in the planning document.
- Introduce new domain concepts (enums, value objects, etc.) not present in plan or standards.
- Generate code that conflicts with the schema DDL.

---

## 3. Output Format: Code Bundle

All generation output MUST use a strict **code bundle** format that can be parsed by the engine.

**Rules:**

- Each file MUST be emitted using a `<<<FILE: ...>>>` marker on its own line.
- For this profile, the file marker MUST contain **filename only** (no package path).  
  Example:
  - `<<<FILE: Tier.java>>>`
  - `<<<FILE: TierRepository.java>>>`
- The file marker line MUST be followed by a newline and then the file's content, indented by exactly 4 spaces.
- The content of each file:
  - MUST be valid Java code.
  - MUST include a correct `package` declaration.
  - MUST compile in isolation given the project's standard dependencies.

Example (illustrative only, not prescriptive):

<<<FILE: Tier.java>>>
    package com.example.global.domain.tier;

    import jakarta.persistence.Entity;
    import jakarta.persistence.Table;

    @Entity
    @Table(schema = "global", name = "tiers")
    public class Tier {
        // ...
    }

<<<FILE: TierRepository.java>>>
    package com.example.global.domain.tier;

    import org.springframework.data.jpa.repository.JpaRepository;

    public interface TierRepository extends JpaRepository<Tier, Long> {
        // ...
    }

The AI MUST NOT:

- Emit prose, commentary, or explanations outside of the code bundle.
- Interleave non-code text between file markers.
- Emit any markers other than the `<<<FILE: ...>>>` lines that declare files.

---

## 4. Repository Behavior & Query Generation

When generating repositories:

- The AI MUST implement **only** the repository methods specified in the approved planning document.
- The AI MUST NOT add "helpful" or "convenience" queries beyond the plan (for example, extra `findAllBy...` methods).
- Method signatures MUST:
  - Use types consistent with the planning document and schema DDL.
  - Respect tenant identifier types and patterns defined in the standards.

For tenant behavior and classification (tenant-scoped vs global vs tenant-entity), the AI MUST:

- Follow the multi-tenancy and repository rules defined in the JPA/database standards document.
- NOT introduce cross-tenant queries or parameters unless explicitly defined in the plan and standards.

---

## 5. Validation Failures (Generation Phase)

If the AI determines that generation cannot proceed safely because of missing or contradictory inputs, it MUST:

- **NOT** emit any `<<<FILE: ...>>>` markers.
- Emit a single-line error message in plain text (no Markdown, no code fences), such as:

  - `VALIDATION FAILED: missing planning document.`
  - `VALIDATION FAILED: inconsistent field types between plan and schema.`

Characteristics of the error message:

- Single line.
- Clearly identifies the issue.
- Contains no file markers or partial code bundles.

This allows the engine to distinguish cleanly between:

- A valid code bundle that can be extracted, and
- An error condition that requires human intervention.

---

## 6. Use of Global Fallback Rules

Whenever the standards bundle and planning document are silent on a specific convention, the AI MUST:

- Consult and apply the shared fallback rules defined in:
  - `templates/_shared/fallback-rules.md`

Examples include:

- Import style when not specified in standards.
- Constructor and accessor patterns when not defined by plan.
- Minimal JavaDoc requirements when not defined elsewhere.

The AI MUST NOT redefine those rules here; it must **reference** and follow them.
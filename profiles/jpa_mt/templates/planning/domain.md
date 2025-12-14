# planning/domain.md

{{include: _shared/base.md}}

{{include: _shared/fallback-rules.md}}

{{include: _phases/planning-guidelines.md}}

---

# Domain Layer Planning Request

_Version: 1.0_  
_Last updated: 2025-12-09_

This planning template is specific to the **domain layer (Entity + Repository)** for a single table in the database schema.

Your task in this phase is to produce a **planning document only**. You MUST NOT generate any code.

## Scope of This Phase

This task is divided into two conceptual phases. In this interaction you are responsible for **Phase 1 only**:

- **Phase 1 – Planning (this template):**
  - Analyze the schema DDL and standards-bundle.
  - Determine the entity and repository design.
  - Document relationships, queries, and open questions.
  - Produce a complete planning document.

- **Phase 2 – Code Generation (separate template, separate request):**
  - NOT part of this interaction.
  - Will consume the approved plan from Phase 1.

You MUST stop after generating the planning document. Do **not** generate `.java` files or any code.

---

## Domain-Specific Planning Requirements

Your planning document MUST cover the following areas:

1. **Schema Analysis**  
   Detailed breakdown of the table structure, keys, constraints, and multi-tenancy pattern.

2. **Entity Design**  
   Plan for the JPA entity class:
   - Class name
   - Package
   - Base class (if any)
   - Field mappings and constraints based on the standards and schema.

3. **Relationship Mapping**  
   Plan for mapping all relevant foreign key relationships:
   - Relationship type (`@ManyToOne`, `@OneToMany`, etc.)
   - Join column(s)
   - Fetch strategy (as defined in the standards / fallbacks).

4. **Repository Design**  
   Plan for the Spring Data JPA repository:
   - Interface name
   - Package
   - Base interface (`JpaRepository` or project-specific base)
   - Standard query methods (per standards)
   - Any custom business queries implied by the schema or domain.

5. **Questions / Clarifications**  
   List of ambiguities, design decisions, or assumptions that require developer input, **after** applying the standards and fallback rules.

---

## Analysis Guidelines

### From Schema DDL

When analyzing the schema DDL, you MUST identify:

- The target table name and its schema.
- All columns, including:
  - Data types
  - Nullability
  - Default values
- The primary key constraint and the column(s) it applies to.
- All foreign key constraints:
  - Local column(s)
  - Referenced table and column(s)
- Other constraints:
  - `UNIQUE`
  - `CHECK`
  - Any other special rules.
- The multi-tenancy pattern based on columns:
  - Does a tenant identifier column exist (`tenant_id`, `org_id`, `client_id`, `company_id`, etc.)?
  - Is this table the tenant/client/org table itself?
  - Is this global/shared data (no tenant identifier column)?

The schema is authoritative. All constraints that appear in the DDL MUST be reflected in your plan unless the standards-bundle explicitly overrides them.

### From Standards Bundle

From `standards-bundle.md` you MUST determine and apply:

- **Package structure conventions**
  - Where domain entities reside.
  - Where repositories reside.
  - Whether entity and repository live in the same package.

- **Base class requirements**
  - Whether entities extend a base class (e.g., `BaseEntity`).
  - What fields and behavior the base class provides (`id`, `publicId`, timestamps, version, soft delete, etc.).
  - Which base-class fields MUST NOT be redeclared in the entity.
  - Whether repositories extend a custom base interface or just `JpaRepository`.

- **Naming conventions**
  - Entity class naming pattern (e.g., singular table name with no suffix).
  - Repository naming pattern (e.g., `<EntityName>Repository`).
  - Field naming conventions (e.g., camelCase derived from snake_case).

- **JPA mapping rules**
  - How to specify schema and table names in `@Table`.
  - Required Java types for timestamps (`OffsetDateTime`, `LocalDateTime`, etc.).
  - Default fetch strategy for relationships (`LAZY` vs `EAGER`).
  - Handling of special data types (JSON/JSONB, enums, etc.).

- **Multi-tenancy patterns**
  - How tenant scoping is enforced (e.g., RLS + current_client_id).
  - What query patterns are required for tenant-scoped vs global entities.

Where the standards are silent, you MUST apply the fallback rules defined earlier in this template instead of asking for clarification.

### Relationship Analysis

For each foreign key:

- Identify the referenced table and infer the related entity class name.
- Determine the likely relationship type:
  - `@ManyToOne` for the owning side (FK holder).
  - `@OneToMany` / `@OneToOne` / `@ManyToMany` where appropriate, if required by standards.
- Check whether the related entity’s Java file is present (if provided as an attachment).
- Plan:
  - Field name on this entity.
  - `@JoinColumn` configuration.
  - Fetch strategy based on standards.
- Respect the relationship modeling fallback rules if the standards do not define a more specific policy.

### Repository Query Planning

You MUST:

- Adhere to any repository base interface and query patterns defined in the standards-bundle.
- Plan standard queries appropriate for the entity type, for example:
  - Lookup by primary key.
  - Lookup by public identifier (UUID) if present.
  - Queries based on unique business keys (e.g., `code`).

For **multi-tenant entities** (columns like `client_id` / `tenant_id` / `org_id`):

- Ensure planned query methods include tenant scoping parameters consistent with the standards.

For **tenant/organization entities** themselves:

- Plan queries that use their business identifiers (e.g., slug, code, etc.), not tenant_id.

For **global/shared entities**:

- Plan queries that use their natural keys or codes (e.g., `code`, `name`, etc.) without tenant parameters.

---

# Output Format

You MUST generate a single planning document in Markdown stored as `planning-response.md`.

## Document Header

Start with a YAML header:

```yaml
---
Generated by: [Your AI model name and version, e.g., "GPT-5.1 Thinking"]
Generated at: [Current UTC timestamp in ISO 8601 format, e.g., "2024-12-08T20:45:32Z"]
---
```

**Important:** Use UTC timezone (trailing `Z`) for the timestamp.

**Document Structure:**
After the header, generate a planning document in Markdown format with the following sections:
```markdown
# Domain Layer Planning Document

## Entity: {{ENTITY}}

**Table:** {{TABLE}}  
**Bounded Context:** {{BOUNDED_CONTEXT}}  
**Multi-Tenancy Model:** [Describe the model identified from schema and fallback rules]

---

## 1. Schema Analysis

### Table: [schema].[table_name]

**Columns identified:**

| Column Name | Type | Constraints | Notes |
|-------------|------|-------------|-------|
| id          | ...  | PRIMARY KEY | [Note if inherited from base class] |
| ...         | ...  | ...         | ...   |

**Primary Key:**
- [List columns comprising the primary key]

**Foreign Keys:**
- `[column_name]` → `[referenced_table].[referenced_column]` – [Description]

**Multi-Tenancy:**
- **Tenant Identifier Column:** `[column_name]` (if any)  
- **Model:** [Tenant-Scoped / Tenant Entity / Global/Shared]

**Special Constraints:**
- [Summarize `UNIQUE`, `CHECK`, and other constraints]

---

## 2. Entity Design Plan

### Package Location
[Full package path for the entity, derived from standards.]

### Entity Class Name
[Entity class name, derived from standards.]

### Base Class
[Base class name (if any) and fields it contributes. Note which fields MUST NOT be redeclared.]

### Fields to Declare

[One subsection per field not inherited from the base class.]

**[fieldName]**: `[JavaType]`  
- **Column:** `[column_name]`  
- **Annotations:** [JPA/validation annotations if relevant for planning]  
- **Constraints:** [Nullability, uniqueness, checks]  
- **Purpose:** [Business meaning of the field]

---

## 3. Relationship Mapping Plan

[One subsection per relationship.]

**Relationship: `[Entity]` → `[RelatedEntity]`**  
- **Type:** `@ManyToOne` / `@OneToMany` / `@OneToOne` / `@ManyToMany`  
- **Field name:** `[relatedEntityFieldName]`  
- **Join Column:** `@JoinColumn(name = "[column_name]")`  
- **Fetch Strategy:** [`LAZY` / `EAGER`]  
- **Purpose:** [What this relationship represents in the domain]

---

## 4. Repository Design Plan

### Repository Class Name
[Name of repository interface, e.g., `TierRepository`.]

### Package Location
[Repository package, typically same as entity.]

### Base Interface
[Base repository interface, e.g., `JpaRepository<Entity, Long>` or project-specific base.]

### Standard Query Methods
[List planned query methods following standards and multi-tenancy rules.]

- `[methodName]([parameters])` – [Short description]

### Custom Business Queries
[List any additional queries implied by the schema/domain.]

**`[methodName]([parameters])`**  
- **Purpose:** [What it does]  
- **Use Case:** [When it’s used]  
- **Implementation:** [Spring Data method name or note if `@Query` likely required]

---

## 5. Special Considerations

**JSON/JSONB Fields:**  
[How they should be mapped according to standards.]

**Enum Fields:**  
[Columns that might map to enums; note any uncertainties in the Questions section.]

**Timestamp Handling:**  
[Planned Java types and which timestamps are DB-managed vs JPA-managed.]

**Soft Delete:**  
[Soft delete strategy if applicable (e.g., `isActive` flag).]

---

## 6. Questions for Developer

[List any remaining ambiguities or decisions that cannot be resolved using the schema, standards-bundle, and fallback rules.]

Examples:
- Columns that may be enums but are not defined as such in standards.
- Conflicting or unclear constraints in the DDL.
- Unclear multi-tenancy implications if schema and standards disagree.

---

## 7. Summary

**Entity Complexity:** [Low / Medium / High]  
**Number of Fields:** [Count of explicitly declared fields]  
**Number of Relationships:** [Count]  
**Multi-Tenancy:** [Tenant-Scoped / Tenant Entity / Global/Shared]  
**Special Features:** [JSON, enums, soft delete, etc., or None]

---

# Pre-Output Validation (AI MUST PERFORM)

Before generating planning-response.md, you MUST internally verify:

1.  ✅ **Schema DDL loaded and analyzed.**
2.  ✅ **Standards bundle read and understood.**
3.  ✅ **Target table for `{{ENTITY}}` found in schema DDL.**
4.  ✅ **All columns, keys, and constraints identified.**
5.  ✅ **Multi-tenancy model determined from schema + standards + fallback rules.**
6.  ✅ **Base class requirements (if any) understood from standards.**
7.  ✅ **Package structure determined from standards.**
8.  ✅ **Naming conventions applied correctly based on standards.**
9.  ✅ **Repository patterns identified from standards.**
10. ✅ **No assumptions made beyond schema + standards + fallback rules.**
11. ✅ **All genuine ambiguities documented in the “Questions for Developer” section.**

If any validation step fails, emit the following message and STOP:
`VALIDATION FAILED: [specific issue]. Could not proceed because: [explanation].`

---

# Instructions to AI Using This Template

**When you receive this planning request:**

1.  **Load and Analyze Inputs:**
    -   `standards-bundle.md`: (coding standards and conventions).
    -   Schema DDL for the target table
    -   Any provided related entity .java files.

2.  **Apply Standards and Fallbacks:**
    -   Always follow the standards-bundle where it defines a rule.
    -   Where the standards are silent, apply the fallback rules in this template.
    -   Do not ask for clarification where a fallback rule applies.

3.  **Create Comprehensive Planning Document:**
    -   Follow the output format exactly.
    -   Document all design decisions and rationale
    -   Ask questions only where the schema, standards, and fallback rules together still leave genuine ambiguity.

4.  **Stop After Planning:**
    -   Do NOT generate any code.
    -   Do NOT create source directories or .java files.
    -   Wait for explicit developer approval before any subsequent phase.
    
---

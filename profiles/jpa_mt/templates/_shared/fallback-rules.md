# Shared Fallback Rules (All Phases)

> These rules define how the AI must behave when the standards bundle or planning documents do not explicitly define a convention.  
> They apply to **all phases** (planning, generation, review, revision) and to all scopes (domain, vertical, service, test).

---

## 1. Truth Sources & Non-Invention

When reasoning about entities, repositories, and queries:

- The AI MUST treat the following as the complete truth source, in this order:
  1. Approved planning document(s) for the current task
  2. Standards bundle (organization-wide standards)
  3. Database schema DDL (for types, nullability, constraints)
- The AI MUST NOT:
  - Invent new fields.
  - Invent new relationships.
  - Invent new domain types (enums, embeddables, value objects) that are not explicitly defined or requested.
- If the schema or planning document is ambiguous, the AI MUST:
  - Surface the ambiguity as a question in the appropriate “Questions for Developer” section (planning), or
  - Refuse to generate or modify code beyond what is unambiguously defined (generation/revision).

---

## 2. Inheritance & Base Entity Rules

- If the standards bundle declares a base entity (e.g., with ID, timestamps, versioning), then:
  - Entities that are designated to use that base MUST extend it.
  - Derived entities MUST NOT redeclare fields that are inherited (e.g., `id`, `createdAt`, `updatedAt`, `version`).
- If no base entity is defined for a given table/entity:
  - The AI MUST NOT invent one.
  - The AI MUST model required fields directly on the entity, based on schema and planning documents.

---

## 3. Import Rules (Global Defaults)

When generating or reviewing Java code:

- `import *` (wildcard imports) MUST NOT be used.
- Unused imports MUST NOT be present in the final code.
- When the standards bundle does not specify import ordering:
  - Imports SHOULD be grouped logically (e.g., Java standard library, then third-party libraries, then project packages).
  - Within each group, imports SHOULD be sorted alphabetically for readability.

These rules apply to all generated or reviewed Java artifacts (entities, repositories, services, tests).

---

## 4. Constructors & Accessors (Global Defaults)

Unless the standards bundle or planning document specifies otherwise:

- Entities MUST provide a JPA-compliant no-argument constructor:
  - Public or protected, as appropriate.
- Entities MAY additionally provide:
  - An all-arguments constructor for convenience.
- The AI MUST NOT:
  - Introduce Lombok annotations (e.g., `@Data`, `@Builder`) unless explicitly allowed in the standards.
  - Introduce builder patterns or fluent APIs that are not requested.

For accessors:

- Standard JavaBean-style getters and setters SHOULD be used for persistent fields, unless the standards define an alternative pattern.
- The AI MUST NOT:
  - Generate non-standard accessor patterns (e.g., fluent setters) without explicit instruction.

These defaults are global and apply wherever Java entities are generated or reviewed.

---

## 5. JavaDoc & Documentation (Global Defaults)

When the standards bundle is silent on documentation style:

- Public classes and interfaces whose purpose is not obvious from the name SHOULD have a brief class-level JavaDoc.
- Public methods that implement non-obvious behavior SHOULD have a short explanatory JavaDoc.
- Boilerplate or trivial methods (e.g., simple getters/setters) DO NOT require JavaDoc unless required by organizational standards.

The AI MUST avoid generating verbose or repetitive documentation that does not add value.

---

## 6. Multi-Tenancy & Tenant Types (Global Interpretation)

- The AI MUST interpret tenant-related types (e.g., IDs, tenant identifiers) using:
  - The schema DDL types (e.g., `BIGINT`, `UUID`), and
  - The mapping rules defined in the standards bundle (e.g., `BIGINT` → `Long`, `UUID` → `java.util.UUID`).
- When generating signatures or fields that involve tenant identifiers, the AI MUST:
  - Use the exact Java type implied by the schema and standards.
  - NOT guess or change tenant identifier types arbitrarily.

Detailed behavioral rules for tenant queries and repositories are defined in the JPA and database standards; this file only defines the global type and non-invention behavior.

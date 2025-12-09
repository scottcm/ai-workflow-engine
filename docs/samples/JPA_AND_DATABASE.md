# Jpa And Database (AI-Optimized)
<!--
tags: [jpa, db, entity, repository, jsonb, timestamp, pagination, performance]
ai-profile: [domain, vertical, service, test, code-review]
-->

> Canonical rules for how entities, IDs, relationships, JSONB, timestamps, and query patterns MUST be implemented.  
> These requirements are optimized for correctness, RLS compatibility, and predictable AI generation.

### Requirements
- Entities MUST explicitly declare schema and table:
    - `@Table(schema = "app", name = "<table>")`
- Entities MUST NOT rely on default schema resolution.
- Entity names MUST remain singular and MUST match the conceptual domain entity.

### Requirements
- Primary keys SHOULD use `Long` or `UUID` per canonical schema definition.
- All persisted timestamps MUST use:
    - `java.time.OffsetDateTime`
- The following MUST NOT be used for persisted timestamps:
    - `LocalDateTime`
    - `java.util.Date`
    - `java.sql.Timestamp`

### Requirements
- Foreign-key relationships:
    - MUST use `@ManyToOne(fetch = FetchType.LAZY)` by default.
    - EAGER fetching is FORBIDDEN unless explicitly justified.
- Raw FK primitive fields MUST NOT coexist with object relationships **unless all are true**:
    - Performance or DTO mapping requires it.
    - Field is `insertable = false, updatable = false`.
    - The intent is documented in a comment or ADR.

### Requirements
- PostgreSQL `jsonb` MUST be mapped using **hypersistence-utils** JSON types:
    - e.g., `@Type(JsonType.class)`
- JSON payloads SHOULD be represented as typed value objects (records/POJOs), not generic maps.

### Requirements
- Simple queries SHOULD use Spring Data method-name queries.
- Complex queries MAY use `@Query` (JPQL or native).
- Dynamic filtering MAY use Specifications **only if standardized**.
- Queries that may return large result sets MUST use:
    - Pagination (`Pageable`)
    - or explicit SQL limits.
- N+1 issues MUST be prevented using:
    - `JOIN FETCH`
    - `@EntityGraph`
    - Projection queries

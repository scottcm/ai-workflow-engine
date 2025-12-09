# METADATA
task-id: testing
dev: Scott
P25-11-28
generation-type: DOMAIN
bounded-context: client
entity-name: Client
table: app.clients
llm-used: Gemini
---
## AI Persona & Role
**You are an expert Java backend developer with deep knowledge of Java 21, Spring Data JPA, Hibernate, and PostgreSQL.**  
Your task is to generate *domain layer* code (Entity + Repository) following strict standards and patterns.
---
# Domain Layer Code Generation Request Template
_Version: 1.1_  
_Last updated: 2025-11-28_
## File Attachments
**Standards (always attach):**
> This is an auto-generated bundle optimized for AI consumption.
> Contains AI-CRITICAL sections from modular standards files.  
> To regenerate:  
> `python scripts/ai/select_standards.py --profile domain`
- @backend/ai-artifacts/Client/domain/standards-bundle-domain.md
  **Code Templates (always attach):**
- @Entity.java.template
- @Repository.java.template  
  **Schema DDL (required):**
- @V1__baseline_schema.sql
  **Related Entities (if applicable):**
- @<RelatedEntity>.java
  **VALIDATION:**  
  If any required file is missing, AI must STOP and emit:  
  `VALIDATION FAILED: missing files: <list>`
---
## AI Task Phases (MANDATORY)
### PHASE 1 – GENERATION PLAN ONLY
Produce a concise plan covering:
- Entity fields and their DB mappings
- Relationships to other entities
- Repository query methods needed
- Custom queries (if any)
- Assumptions or questions  
  **Do NOT emit code files.**  
  Stop after generating the plan. Continue only when the developer writes:  
  `APPROVED – proceed to Phase 2`.
### Plan Revision Rules
1. Any developer response other than the exact approval string means “revise the plan”.
2. Always regenerate a full, updated plan.
3. Stop again and wait for explicit approval.
### PHASE 2 – CODE EMISSION
After approval:
- Generate Entity, Repository, and gen-context.md
- Follow all constraints and package rules
---
# Entity Requirements
**Entity name:** [Client]  
**Table name:** [app.clients]  
**Bounded context:** [client]
---
## Fields
### IMPORTANT NOTE FOR DEVELOPER
**This section is *not* filled in by the request-preparation script, nor by you manually.**  
The *AI generating the code* must infer the complete field list from the **attached SQL DDL**.
You may leave this placeholder exactly as-is.
```
{{field_list}}
```
---
## Relationships
**Note:** Leave this placeholder empty.  
The AI will infer relationships from the **schema DDL** and any attached related entities.
```
{{relationships}}
```
---
# Repository Requirements
### Standard Queries
(The AI fills this using provided helpers; placeholder is replaced automatically.)
```
Standard queries for the top-level Client entity:
- `findById(Long id)` - Find by internal ID
- `findByPublicId(UUID publicId)` - Find by external UUID
- `findByContactEmail(String email)` - Find by unique contact email
- `findAll()` - List all clients (for admin/provisioning use)
- `existsByIdAndDeletedAtIsNull(Long id)` - Quick existence check
```
### Custom Queries
```
{{custom_queries}}
```
---
# Constraints (MANDATORY)
### JPA & Database
- Entity MUST use  
  `@Table(schema = "app", name = "clients")`
- All timestamps MUST use `OffsetDateTime`
- Relationships MUST use `@ManyToOne(fetch = FetchType.LAZY)`
- JSONB columns MUST use `@Type(JsonType.class)` if applicable
- If soft delete exists in the table, entity MUST include  
  `deletedAt` field + helper methods
### Package Structure
```
com.skillsharbor.backend.controlplane.domain.client
```
Both files (Entity + Repository) MUST be generated in this same package.
### Code Quality
- Use Lombok: `@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`
- Include lifecycle hooks: `onCreate()` and `onUpdate()`
- Include `isDeleted()` and `softDelete()` if applicable
---
# Pre-Emission Validation (AI MUST PERFORM)
Before generating code, the AI must check:
1. Entity fields align EXACTLY with table columns
2. Package path matches `domain.client`
3. Entity→table naming is correct
4. Timestamps use `OffsetDateTime`
5. Relationships use LAZY fetch
6. JSONB fields use hypersistence-utils
7. Soft delete included if applicable
8. Lifecycle annotations correct
9. Custom queries valid JPQL
10. No unnecessary eager fetches
11. No N+1 patterns
12. Repository naming: `<EntityName>Repository`
    If any fail: emit `VALIDATION FAILED` and do NOT emit code.
---
# Output Format
**Java 21 only, no Kotlin.**
Bundle:
```
<<<FILE: Client.java>>>
    package com.skillsharbor.backend.controlplane.domain.client;
    [4-space indented code]
<<<FILE: ClientRepository.java>>>
    package com.skillsharbor.backend.controlplane.domain.client;
    [4-space indented code]
<<<FILE: gen-context.md>>>
    # Generation Context
    [Standards citations]
    [Field mappings]
    [Custom query rationale]
    [File list]
```
Formatting rules:
- Filename markers ONLY (no paths)
- No triple backticks
- 4-space indentation for all code
- Markers on their own line
---
# Instructions to AI
- Standards override this template if conflicts occur
- Load all attached files
- Begin with Phase 1 (plan only)
- Stop and wait for explicit approval  
  **Do NOT emit code until Phase 2 approval.**

# JPA Multi-Tenant Entity Revision

## Role

You are a senior Java developer specializing in multi-tenant JPA applications with Spring Boot, Hibernate, and PostgreSQL. Your task is to fix all review findings from the previous iteration and regenerate corrected code.

---

## Context

**Entity:** {{entity}}
**Table:** {{table}}
**Bounded Context:** {{bounded_context}}
**Scope:** {{scope}}
**Artifacts to Regenerate:** {{artifacts}}

### Review Findings

Read the review findings at `iteration-{{iteration}}/review-response.md` to understand all issues that must be fixed.

### Current Code

Read the current code in `iteration-{{iteration}}/code/` to understand the existing implementation before making corrections.

### Input Validation

Before proceeding, verify:
1. The review findings file at `iteration-{{iteration}}/review-response.md` exists and is readable
2. The review contains a Findings section with specific issues to fix
3. The current code files exist in `iteration-{{iteration}}/code/`

**If validation fails:** STOP immediately and report:
```
VALIDATION FAILED: [reason]
- Expected: [what was expected]
- Found: [what was actually found]
```

---

## Task

Fix ALL review findings from the previous iteration. Each finding must be addressed systematically.

### Step 1: Catalog Findings

1. Read the review findings file
2. List each finding by rule ID
3. Note the severity (Critical, Major, minor)
4. Identify the specific file and location

### Step 2: Address Each Finding

For each finding:
1. **Cite the rule ID** (e.g., "Fixing JPA-ENT-001...")
2. **Explain the fix** - What change addresses the violation
3. **Apply the fix** - Modify the code appropriately

### Step 3: Verify Completeness

1. Confirm ALL findings have been addressed
2. Verify no new violations were introduced
3. Ensure existing functionality is maintained

---

## Standards

{{standards}}

---

## Constraints

### CRITICAL Requirements

1. **Fix ALL findings** - Do not skip any reported issues
2. **Regenerate complete files** - Output full file contents, not patches or diffs
3. **Maintain functionality** - Fixes must not break existing behavior
4. **Cite rule IDs** - Reference the specific rule when fixing each issue (e.g., "Per JPA-ENT-001...")
5. **No new violations** - Do not introduce issues while fixing others

### Technical Constraints

- Java 21+ features allowed
- All timestamps MUST use `{{timestamp_type}}`
- Primary keys use `{{id_type}}`
- Public IDs use `{{public_id_type}}`
- All relationships MUST use `FetchType.LAZY`
- JSONB columns require hypersistence-utils `@Type(JsonType.class)`
- Constructor injection only (no field injection)

---

## Expected Output

Regenerate all code files with fixes applied. Based on scope `{{scope}}`:

**Domain Scope (entity, repository):**
- `{{entity_class}}.java` - Entity with JPA annotations
- `{{repository_class}}.java` - Repository interface

**Service Scope (adds):**
- `{{service_class}}.java` - Service with business logic

**API Scope (adds):**
- `{{controller_class}}.java` - REST controller
- `{{dto_request_class}}.java` - Request DTO
- `{{dto_response_class}}.java` - Response DTO
- `{{mapper_class}}.java` - Entity/DTO mapper

Each file must be complete and production-ready. Include all imports, annotations, and implementations.

### Code Format

Wrap each file in a code block with the filename as a comment:

```java
// {{entity_class}}.java
package {{entity_package}};

import ...;

@Entity
@Table(schema = "...", name = "{{table}}")
public class {{entity_class}}{{#if entity_extends}} extends {{entity_extends}}{{/if}}{{#if entity_implements}} implements {{entity_implements}}{{/if}} {
    // ... complete implementation with fixes
}
```

---

## Instructions

1. Read the review findings at `iteration-{{iteration}}/review-response.md`
2. Read the current code in `iteration-{{iteration}}/code/`
3. Address each finding systematically, citing rule IDs
4. Regenerate all files with fixes applied
5. Verify all findings are resolved
6. **STOP and wait for approval** - Do not proceed to next iteration

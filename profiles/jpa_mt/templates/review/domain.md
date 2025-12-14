{{include: _shared/base.md}}
{{include: _shared/fallback-rules.md}}
{{include: _phases/review-guidelines.md}}

---

# Domain Layer Review

## Scope Definition

You are reviewing **domain layer** artifacts:
- **Entity class(es)** - Data model implementation
- **Repository interface(s)** - Data access contracts

This scope does NOT include:
- Service layer logic
- Controller/API layer
- DTOs or mapping logic

---

## Expected Artifacts

Based on the approved plan, you should find:

**Entity Files:**
- One or more entity class files
- File names matching entity names from plan
- Located in code generation output directory

**Repository Files:**
- One or more repository interface files  
- Naming pattern: `{Entity}Repository`
- Located in code generation output directory

**If artifacts are missing or don't match the plan, this is CRITICAL.**

---

## Review Organization

Structure your review by artifact type:

### 1. Entity Review

For each entity class, validate:
- Implements data model from plan
- Follows standards bundle requirements for entities
- All planned fields present with correct types
- Field types match plan and schema (if provided)
- No extra fields not in plan

### 2. Repository Review

For each repository interface, validate:
- Provides data access methods from plan
- Method signatures match plan specifications
- Follows standards bundle patterns for repositories
- No extra methods not in plan

### 3. Integration Review

Cross-cutting validation:
- Entities and repositories work together correctly
- Relationships properly defined
- References between artifacts are valid
- Implementation matches approved design

---

## Domain-Specific Focus

The standards bundle defines requirements for:
- Entity structure and annotations
- Repository patterns and method naming
- Data access security and isolation
- Field and class naming conventions

**Apply standards bundle requirements to domain artifacts only.**

**Do NOT review:**
- Service layer concerns (business logic)
- API contracts (controller layer)
- Data transfer or mapping (DTO layer)

These are out of scope for domain layer review.

---

## Review Completion

Your review MUST answer these questions:

- [ ] Are all planned domain artifacts present?
- [ ] Do they implement the approved plan exactly?
- [ ] Do they follow all standards bundle requirements?
- [ ] Are there scope violations (e.g., business logic in entities)?
- [ ] Do artifacts integrate correctly?

Focus exclusively on domain layer. Other layers reviewed separately.
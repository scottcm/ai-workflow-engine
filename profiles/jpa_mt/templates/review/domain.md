{{include: _shared/base.md}}
{{include: _shared/fallback-rules.md}}
{{include: _phases/review-guidelines.md}}

---

# Domain Layer Review Request

## Scope Definition

You are reviewing the **domain layer** artifacts:
- **Entity class(es)** - Data model implementation
- **Repository interface(s)** - Data access contracts

This scope does NOT include:
- Service layer
- Controller layer
- DTOs or mappers

---

## Expected Artifacts

Based on the plan, you should find:

**Entity files:**
- One or more entity class files
- File names should match entity names from plan

**Repository files:**
- One or more repository interface files
- File names should match `{Entity}Repository` pattern

If artifacts are missing or don't match the plan, this is a CRITICAL issue.

---

## Review Organization

Organize your review by artifact type:

### 1. Entity Review
For each entity class:
- Does it implement the data model from the plan?
- Does it follow the standards bundle requirements?
- Are all planned fields present?
- Are field types correct per plan/schema?

### 2. Repository Review  
For each repository interface:
- Does it provide the data access methods from the plan?
- Are method signatures correct?
- Does it follow standards bundle patterns?

### 3. Integration Review
- Do entities and repositories work together correctly?
- Are relationships properly mapped?
- Does the implementation match the approved design?

---

## Domain-Specific Validation

The standards bundle defines requirements for:
- Entity structure and annotations
- Repository patterns and methods
- Data access security
- Naming conventions

Apply those standards to domain layer artifacts only.
Do NOT review service logic, API contracts, or presentation concerns - those are out of scope.

---

## Review Completion

Your review MUST answer:
- Are all planned domain artifacts present?
- Do they implement the approved plan exactly?
- Do they follow the standards bundle requirements?
- Are there any scope violations (e.g., service logic in entities)?

Focus only on domain layer concerns. Other layers will be reviewed separately.
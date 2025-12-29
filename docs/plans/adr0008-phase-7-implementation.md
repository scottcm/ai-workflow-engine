# Phase 7: Template Cleanup - Implementation Guide

**Goal:** Remove engine concerns from profile templates.

**Dependencies:** Phases 5 (Engine Prompt Assembly) and 6 (WritePlan Simplification)

---

## Overview

Profile templates currently contain:
1. Output destination instructions ("Save as `generation-response.md`...")
2. Session artifact path references (`@.aiwf/sessions/{{SESSION_ID}}/plan.md`)
3. Engine variables for path construction (`{{SESSION_ID}}`, `{{ITERATION}}`)

These are now engine responsibilities (handled by `PromptAssembler`). Remove them from templates.

---

## Patterns to Remove

### 1. Output Destination Sections

**Pattern:** Lines instructing where to save the response.

**Examples:**
```markdown
## Output Destination

Save your complete code bundle as `generation-response.md` to same location as `generation-prompt.md`.
```

```markdown
## Output Destination

Save your complete planning document as `planning-response.md` to same location as `planning-prompt.md`.
```

**Action:** Delete these sections entirely. Engine provides output instructions.

---

### 2. Session Artifact References

**Pattern:** File references to session-managed artifacts.

**Examples:**
```markdown
## Required Attachments

- Approved Plan: @.aiwf/sessions/{{SESSION_ID}}/plan.md
- Standards Bundle: @.aiwf/sessions/{{SESSION_ID}}/standards-bundle.md
- Schema DDL: @{{SCHEMA_FILE}}
```

**Action:**
- Remove plan and standards bundle references (engine injects these)
- Keep schema DDL reference (profile-owned, from context)

**After:**
```markdown
## Required Attachments

- Schema DDL: @{{SCHEMA_FILE}}
```

Or if only schema remains, simplify:
```markdown
## Schema

{{SCHEMA_DDL}}
```

---

### 3. Session Path Variables

**Pattern:** Variables used to construct session paths.

**Examples:**
- `{{SESSION_ID}}` in path construction
- `{{ITERATION}}` in path construction

**Action:** Remove these from path references. If used for informational purposes only (not paths), they can remain in metadata blocks.

---

## Files to Update

### 1. `profiles/jpa_mt/templates/_shared/base.md`

**Current content includes:**
```yaml
---
# METADATA
session-id: {{SESSION_ID}}
iteration: {{ITERATION}}
...
---
```

**Decision:** Keep as informational metadata (not used for paths). This is profile metadata for context, not engine path construction.

**No change required** if only used for display/context.

---

### 2. `profiles/jpa_mt/templates/_phases/generation-guidelines.md`

**Remove:**
```markdown
## Required Attachments

- Approved Plan: @.aiwf/sessions/{{SESSION_ID}}/plan.md
- Standards Bundle: @.aiwf/sessions/{{SESSION_ID}}/standards-bundle.md
- Schema DDL: @{{SCHEMA_FILE}}
```

**Replace with reference to engine-provided inputs:**
```markdown
## Required Inputs

This prompt includes:
- The approved planning document
- The standards bundle
- Your schema DDL

These are provided in the sections above. If any is missing, emit validation failure.
```

---

### 3. `profiles/jpa_mt/templates/generation/domain.md`

**Remove:**
```markdown
## Output Destination

Save your complete code bundle as `generation-response.md` to same location as `generation-prompt.md`.
```

**Keep:** Everything else (task description, validation rules, format instructions).

---

### 4. `profiles/jpa_mt/templates/generation/vertical.md`

Same changes as `domain.md`.

---

### 5. `profiles/jpa_mt/templates/planning/domain.md`

**Remove:**
```markdown
## Output Destination

Save your complete planning document as `planning-response.md` to same location as `planning-prompt.md`.
```

---

### 6. `profiles/jpa_mt/templates/planning/vertical.md`

Same changes as `domain.md`.

---

### 7. `profiles/jpa_mt/templates/review/domain.md`

**Remove:**
```markdown
## Output Destination

Save your complete review as `review-response.md` to same location as `review-prompt.md`.
```

---

### 8. `profiles/jpa_mt/templates/review/vertical.md`

Same changes as `domain.md`.

---

### 9. `profiles/jpa_mt/templates/revision/domain.md`

**Remove:**
```markdown
## Output Destination

Save your complete code bundle as `revision-response.md` to same location as `revision-prompt.md`.
```

---

### 10. `profiles/jpa_mt/templates/revision/vertical.md`

Same changes as `domain.md`.

---

## Patterns to KEEP

### 1. Domain Variables

Keep all domain-specific variables:
- `{{ENTITY}}`
- `{{TABLE}}`
- `{{BOUNDED_CONTEXT}}`
- `{{SCHEMA_DDL}}`
- `{{DEV}}`
- `{{TASK_ID}}`
- `{{DATE}}`
- `{{SCOPE}}`

These come from context and are profile's responsibility.

---

### 2. Output Format Instructions

Keep instructions about response format (profile parses these):

```markdown
## Output Format: Code Bundle

All output MUST use a strict **code bundle** format that can be parsed by the engine.

**Rules:**
- Each file MUST be emitted using a `<<<FILE: ...>>>` marker on its own line
...
```

---

### 3. Review Metadata Format

Keep `@@@REVIEW_META` block instructions:

```markdown
Include a metadata block at the end of your review:

@@@REVIEW_META
verdict: PASS | FAIL
issues_total: N
issues_critical: N
...
@@@
```

---

### 4. Standards Application Instructions

Keep instructions about how to apply standards:

```markdown
## Standards Authority Rule

If there is any conflict between:
- instructions in this prompt
- fallback rules
- or phase-specific guidance

and the **standards-bundle**, the **standards-bundle ALWAYS takes precedence**.
```

---

## Step-by-Step Cleanup

For each template file:

1. **Search for "Output Destination"** - Remove entire section
2. **Search for `@.aiwf/sessions/`** - Remove session artifact references
3. **Search for `{{SESSION_ID}}`** - Remove if used for path construction; keep if informational only
4. **Search for `{{ITERATION}}`** - Same as SESSION_ID
5. **Verify domain variables remain** - `{{ENTITY}}`, `{{TABLE}}`, etc.
6. **Verify format instructions remain** - `<<<FILE:>>>`, `@@@REVIEW_META`
7. **Update "Required Attachments"** sections to reference engine-provided inputs

---

## Testing Requirements

**File:** `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py`

1. Test templates render without session path variables
2. Test templates don't contain output destination instructions
3. Test templates still contain domain variables
4. Test templates still contain format instructions

**File:** `tests/integration/test_workflow_orchestrator.py`

5. Test assembled prompts include engine-provided artifacts
6. Test assembled prompts include output instructions
7. Test end-to-end workflow with cleaned templates

---

## Verification Checklist

After cleanup, verify no template contains:

- [ ] `@.aiwf/sessions/` (session artifact paths)
- [ ] `Save your complete response to` or similar
- [ ] `Save your complete code bundle as` or similar
- [ ] `generation-response.md` as output filename
- [ ] `planning-response.md` as output filename
- [ ] `review-response.md` as output filename
- [ ] `revision-response.md` as output filename

Templates should still contain:

- [ ] `{{ENTITY}}`, `{{TABLE}}`, `{{BOUNDED_CONTEXT}}`, etc.
- [ ] `{{SCHEMA_DDL}}`
- [ ] `<<<FILE: filename>>>` format instructions
- [ ] `@@@REVIEW_META` format instructions
- [ ] Standards application rules

---

## Files Changed

| File | Change |
|------|--------|
| `profiles/jpa_mt/templates/generation/domain.md` | Remove output destination |
| `profiles/jpa_mt/templates/generation/vertical.md` | Remove output destination |
| `profiles/jpa_mt/templates/planning/domain.md` | Remove output destination |
| `profiles/jpa_mt/templates/planning/vertical.md` | Remove output destination |
| `profiles/jpa_mt/templates/review/domain.md` | Remove output destination |
| `profiles/jpa_mt/templates/review/vertical.md` | Remove output destination |
| `profiles/jpa_mt/templates/revision/domain.md` | Remove output destination |
| `profiles/jpa_mt/templates/revision/vertical.md` | Remove output destination |
| `profiles/jpa_mt/templates/_phases/generation-guidelines.md` | Remove artifact refs, update input section |
| `profiles/jpa_mt/templates/_shared/base.md` | Review (likely no change) |
| `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py` | Updated tests |
| `tests/integration/test_workflow_orchestrator.py` | Updated tests |

---

## Acceptance Criteria

- [ ] No template contains output destination instructions
- [ ] No template contains `@.aiwf/sessions/` paths
- [ ] Domain variables (`{{ENTITY}}`, etc.) still work
- [ ] Format instructions (`<<<FILE:>>>`, `@@@REVIEW_META`) preserved
- [ ] Standards application instructions preserved
- [ ] Templates render correctly with prompt assembler
- [ ] All tests pass
# Phase 3 Implementation Plan: Code Generation Step (Updated)

**Project:** AI Workflow Engine  
**Profile:** JPA Multi‑Tenant (JPA‑MT)  
**Phase:** 3 — Code Generation  
**Scope:** Domain Layer (Entity + Repository)  
**Updated To Reflect Agreements:**  
- FILE markers contain **filename only**  
- Extracted files written under **.aiwf/sessions/{session-id}/iteration-N/code/**  
- Use **WorkflowPhase.PLAN_APPROVED** when generating code  
- BundleExtractor returns `{filename → content}`  
- Engine does *not* attempt package placement; developer reviews output and moves files  

---

# 1. Current State

## 1.1 Completed (From Phase 2)
- Profile configuration (`config.yml`)
- Layered template architecture (`_shared/`, `_phases/`, scope templates)
- Template include resolver (`_resolve_template_includes`)
- Template renderer (`TemplateRenderer`)
- Planning template (`planning/domain.md`)
- All Phase 2 tests passing

## 1.2 Supporting Infrastructure
- Local PostgreSQL test database (Docker)
- Generic standards bundle (multi‑tenant JPA/Spring)
- Real planning responses validated through Gemini and ChatGPT

---

# 2. Objective of Phase 3

Implement the **code generation step**:

```
PLAN_APPROVED → GENERATION_REQUEST → AI → GENERATION_RESPONSE → Extracted Code Artifacts
```

The engine must:

### ✔ Render a generation template  
### ✔ Allow the developer to submit it to an AI manually  
### ✔ Extract Java source files from the returned bundle  
### ✔ Store artifacts cleanly under the session + iteration directory  

**Not included in this phase:**
- Review step  
- Revision step  
- Full workflow orchestration  
- Automatic provider integration  
- CLI command set  

This is a **manual-mode generation** step.

---

# 3. Architectural Placement

From ADR‑0001, the Phase 3 components live here:

```
Interface Layer (CLI) — NOT IN SCOPE
↓
Application Layer — NOT IN SCOPE
↓
Domain Layer (Core Logic)
    • TemplateRenderer (exists)
    • BundleExtractor (new)
    • FileWriter (new)
↓
Infrastructure Layer
    • Filesystem output (iteration folders)
```

And all artifacts go into:

```
.aiwf/
  sessions/
    {session-id}/
      iteration-N/
        planning-prompt.md
        planning-response.md
        generation-prompt.md
        generation-response.md
        code/
          Tier.java
          TierRepository.java
```

---

# 4. Components to Implement

# 4.1 Generation Phase Guideline Template  
**File:** `profiles/jpa_mt/templates/_phases/generation-guidelines.md`

Purpose: defines global instructions for code generation.

Contains:
- Task definition (“Implement approved plan exactly”)
- Required inputs:
  - `planning-response.md`
  - `standards-bundle.md`
- Hard rules:
  - MUST follow the approved plan  
  - MUST follow standards  
  - MUST emit compilable, idiomatic Java  
  - MUST output bundle using filename-only FILE markers  
- MUST NOT:
  - Add new fields, relationships, decisions  
  - Deviate from plan or invent conventions  
- Output format:
  ```
  <<<FILE: Tier.java>>>
      package ...

      public class Tier {
          ...
      }
  ```
- Validation checklist for code generators

---

# 4.2 Domain Generation Template  
**File:** `profiles/jpa_mt/templates/generation/domain.md`

Structure:

```
{{include: _shared/base.md}}
{{include: _shared/fallback-rules.md}}
{{include: _phases/generation-guidelines.md}}

---

# Domain Layer Code Generation Request

(… domain-specific sections here …)
```

Must specify:
- Entity generation rules
- Repository generation rules
- How to interpret the plan
- How to name files (filename only)
- Example correct bundle

---

# 4.3 BundleExtractor  
**File:** `profiles/jpa_mt/bundle_extractor.py`

**FILE markers contain filename only.**

### Format supported:
```
<<<FILE: Tier.java>>>
    package ...

    public class Tier {}
<<<FILE: TierRepository.java>>>
    package ...

    public interface TierRepository {}
```

### Responsibilities:
- Extract file segments using regex  
- Strip leading 4-space indentation  
- Validate:
  - filename only  
  - non-empty content  
  - contains a `package` statement  
- Return dict:
  ```python
  {
      "Tier.java": "package ...",
      "TierRepository.java": "package ..."
  }
  ```

### Errors:
- No FILE markers → `ValueError`
- Bad filenames → `ValueError`
- Empty file blocks → `ValueError`

---

# 4.4 FileWriter  
**File:** `profiles/jpa_mt/file_writer.py`

Writes extracted files to:

```
.aiwf/sessions/{session-id}/iteration-N/code/
```

Rules:
- Create directory if missing  
- Sanitize filename (no slashes, traversal, unicode weirdness)  
- Write UTF‑8  
- Return list of written paths  
- Confirm existence after writing  

This writer does **not** create packages; it's for artifact management only.

---

# 4.5 Helper Script: Generate Code Prompt  
**File:** `scripts/generate_code_manual.py`

Steps:
1. Load session state
2. Use TemplateRenderer
3. Use phase: **WorkflowPhase.PLAN_APPROVED**
4. Write `generation-prompt.md` to iteration folder
5. Print developer instructions:
   ```
   Send planning-response.md + generation-prompt.md + standards-bundle.md to the AI
   ```

### Session State Requirement (Manual Mode)

Helper scripts assume a valid session directory already exists.

A valid manual-mode session requires:

- A session directory at:  
  `.aiwf/sessions/{session-id}/iteration-{n}/`
- A previously generated `planning-response.md` in that iteration directory  
  (required as the authoritative input to code generation).
- Context metadata supplied either:
  - From an existing `session.json` (if present), or
  - Via user input prompts (entity name, table name, bounded context, etc.)

The helper scripts **do not** create or modify workflow state beyond writing rendered templates and extracted code artifacts.  
They operate strictly within the iteration directory in accordance with ADR-0001.

---

# 4.6 Helper Script: Extract Code  
**File:** `scripts/extract_code_manual.py`

Steps:
1. Read `generation-response.md`
2. Run BundleExtractor
3. Run FileWriter
4. Output results:
   ```
   Extracted 2 files:
       Tier.java
       TierRepository.java
   Written to: .aiwf/sessions/.../iteration-N/code/
   ```

These allow testing **before** the full engine is built.

## 4.7 Phase 3 Generation Step Contract

This section defines the **explicit contract** for the Phase 3 “generation step” used by
manual helper scripts and future automated orchestration.

### 4.7.1 Scope

This contract applies **only to Phase 3** and exists to support:

- Manual generation workflows (helper scripts)
- Reuse by future orchestration in Phase 5+

It does **not** define global workflow orchestration.

---

### 4.7.2 Immutability Rule (Phase 3)

- Phase 3 tooling **MUST NOT** modify or persist `WorkflowState`.
- No updates to `session.json` occur during Phase 3.
- Phase 3 outputs are limited to:
  - Generated code files written to disk
  - In-memory artifact metadata returned to the caller

State mutation and persistence are deferred to Phase 5 orchestration.

---

### 4.7.3 Generation Step Function

The Phase 3 generation logic **MUST** be implemented as a reusable function
(callable by helper scripts and future orchestration).
- Accept: (easier to test)
  - `bundle_content: str` — raw AI output
  - `session_dir: Path` — per-session directory
  - `iteration: int` — iteration number
  - `extractor: Callable[[str], dict[str, str]]` — bundle parser
  - `writer: Callable[[Path, dict[str, str]], list[Path]]` — file writer

#### Responsibilities

The generation step function **MUST**:

- Accept:
  - `bundle_content: str` — raw AI output containing `<<<FILE: ...>>>` markers
  - `session_dir: Path` — the per-session directory  
    `.aiwf/sessions/{session-id}`
  - `iteration: int` — iteration number (1, 2, 3, …)
- Use profile-specific bundle parsing (directly or via an injected extractor).
- Write extracted files to:
  - `{session_dir}/iteration-{iteration}/code/`
- Return a list of `Artifact` records representing generated code files.

#### Non-Responsibilities

The generation step function **MUST NOT**:

- Accept or mutate `WorkflowState`
- Read `generation-response.md` from disk
- Persist workflow state or session metadata
- Perform global workflow orchestration

---

### 4.7.4 Artifact Path Semantics

- `Artifact.file_path` **MUST** be stored as a string path **relative to
  `session_dir`**.
- Absolute paths are forbidden.
- The `session-id` **MUST NOT** be embedded redundantly in `file_path`.

**Example:**
```
iteration-1/code/Tier.java
```

---

### 4.7.5 Error Handling

- Empty or whitespace-only `bundle_content` **MUST** raise `ValueError`.
- Bundle parsing errors **MUST** propagate as `ValueError`.
- File writing errors **MUST** propagate without being swallowed.
- On any error, **no partial writes are allowed**.
  - Fail-fast behavior provided by `FileWriter` is relied upon.

---

### 4.7.6 Relationship to Helper Scripts

- Phase 3 helper scripts:
  - Locate and read `generation-response.md`
  - Invoke the generation step function
  - Display results to the user
- Helper scripts **DO NOT** update or persist workflow state.

---

### 4.7.7 Relationship to Future Orchestration

- Phase 5+ orchestration:
  - Invokes the same generation step function
  - Consumes returned `Artifact` records
  - Mutates and persists `WorkflowState`

This separation is intentional and required.

## 4.8 Component Dependencies

The code generation workflow involves a clear sequence of responsibilities.  
The diagram below shows how each Phase 3 component fits together:
```
TemplateRenderer (existing)
↓ renders
generation/domain.md (template)
↓ produces
generation-prompt.md
↓ manual step (developer sends to AI)
generation-response.md
↓ parsed by
BundleExtractor (new)
↓ produces extracted file map
FileWriter (new)
↓ writes files to
.aiwf/sessions/{session-id}/iteration-N/code/
```

**Notes:**
- Templates define *instructions*; the renderer produces the **prompt** sent to the AI.
- The bundle extractor and file writer operate strictly on *AI output*, never regenerating or modifying code.
- This satisfies ADR-0001’s rule: _templates describe behavior; infrastructure components manipulate artifacts_.


---

# 5. Implementation Order

```
1. Create generation-guidelines.md
2. Create generation/domain.md
3. Manual template tests (Gemini / ChatGPT)
4. Implement BundleExtractor + unit tests
5. Implement FileWriter + unit tests
6. Write helper scripts
7. End-to-end manual validation
```

Estimated time: **4–5 days**.

---

# 6. Testing Strategy

## 6.1 Unit Tests

### BundleExtractor
```
test_extract_valid_bundle()
test_extract_invalid_bundle()
test_extract_empty_block()
test_extract_multiple_files()
test_extract_filename_only_rules()
```

### FileWriter
```
test_write_files()
test_filename_sanitization()
test_directory_creation()
```

### Template Rendering
```
test_render_generation_template()
```

---

## 6.2 Integration Test
Full workflow:

1. Load planning-response.md  
2. Render generation template  
3. Use a saved real AI output  
4. Extract files  
5. Write to iteration directory  
6. Verify Java compiles  

---

# 7. Success Criteria

The generation step is considered complete and correct when all of the following criteria are satisfied:

- ✅ **Generated Java code compiles in isolation** within a minimal test project.
  - Only JDK, Spring Framework, Spring Data JPA, and Jakarta Persistence API may be assumed.
  - No requirement to integrate with or compile against a larger application codebase.
  - No additional shared infrastructure (e.g., BaseEntity) is required unless explicitly planned.

- ✅ **Generated code conforms exactly to the approved planning document.**
  - No additional methods, fields, annotations, or behaviors beyond what the plan defines.
  - All fields, relationships, repository methods, and constraints in the plan are implemented.

- ✅ **Generated code follows the standards bundle.**
  - Naming, JPA annotations, package structure, timestamps, enums, boilerplate, and DI rules.
  - No deviations unless explicitly specified in the planning document.

- ✅ **The output bundle uses the strict filename-only `<<<FILE:>>>` format.**
  - Each file is emitted using filename only (no package paths).
  - Each file's content is correctly 4-space-indented.
  - The bundle contains no extra prose, commentary, or explanations.

- ✅ **BundleExtractor successfully extracts all files from the AI response.**
  - No missing markers.
  - No malformed markers.
  - Each extracted file is non-empty and contains valid Java code.

- ✅ **FileWriter successfully writes extracted code files to the iteration directory.**
  - Files are written under:  
    `.aiwf/sessions/{session-id}/iteration-{n}/code/`
  - Filenames are sanitized.
  - All files are readable after write.

- ✅ **End-to-end manual workflow succeeds.**
  - Planning document → generation prompt  
  - Prompt → AI response  
  - AI response → extracted files  
  - Extracted files → successful compilation  

- ✅ **All Phase 3 unit tests and integration tests pass.**
  - Template rendering tests  
  - Bundle extraction tests  
  - File writing tests  
  - Full workflow test (non-AI simulation)


---

# 8. Risks & Mitigation

### AI deviates from bundle format  
Mitigation: strong examples, reject incorrect output.

### Invalid Java generated  
Mitigation: ensure the generation template references standards precisely.

### Naming collisions  
Mitigation: filename-only extraction inside isolated iteration dirs avoids conflicts.

### Multi-provider variation  
Mitigation: test with both Gemini and ChatGPT real samples.

---

# 9. Out of Scope

- Automated provider integrations  
- Review step  
- Revision step  
- Complete workflow orchestration  
- CLI command suite  

---

# 10. Next Steps After Phase 3

1. Build Review workflow  
2. Build Revision workflow + iteration chaining  
3. Implement Workflow Orchestrator  
4. Implement CLI interface  
5. Add automatic provider execution  

---

**End of Document**

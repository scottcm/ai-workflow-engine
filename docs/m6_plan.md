# M6 Plan — CLI Surface for aiwf (Click) + Minimal UX for Manual & Automated Workflows

> Status: Draft for implementation review  
> Assumptions (locked for M6):  
> - The end-user entrypoint binary is `aiwf` (CLI).  
> - CLI is implemented with **Click**.  
> - Engine orchestration semantics and phase model are **locked after M5** (including `REVISED`, `*ING/*ED` split, artifact-gated `step()`).  
> - Profiles remain unchanged; CLI must not introduce profile logic leakage.  
> - Pydantic state validation is **deferred post‑M5** (ADR‑0003 marked deferred). M6 may optionally introduce boundary validation as a follow-on slice if approved.

---

## 1. Scope

### 1.1 What M6 Adds
M6 introduces a **thin, user-facing CLI** that:
1. Initializes a workflow session (calls `WorkflowOrchestrator.initialize_run`).
2. Advances a session deterministically (calls `WorkflowOrchestrator.step`).
3. Reports session status and “what to do next” for manual workflows.
4. Sets stable exit codes for automation/CI scripting.

### 1.2 What M6 Does Not Add
- No changes to engine phase semantics, iteration semantics, or profile behavior.
- No integration/provider automation that bypasses the “artifact drop” manual flow.
- No “redo phase” command in the public surface area (keep out of M6 unless required).
- No migration of WorkflowState to Pydantic in this milestone unless explicitly elevated.

---

## 2. Primary Commands (M6 Core)

### 2.1 `aiwf init`
**Purpose:** Create a new workflow session (but do not “run” it).

**Inputs (required):**
- `--scope <value: str>`
- `--entity <value: str>`
- `--table: <value: str>`
- `--bounded-context: <value: str>`

** Inputs (optional):**
- `--dev <value: str>`
- `--taskid <value: str>`

**Behavior:**
- Calls `WorkflowOrchestrator.initialize_run(profile=..., scope=..., entity=..., ...)` with the CLI-supplied inputs.
- Prints the `session_id` to stdout (single line, machine-friendly).
- Returns exit code 0 on success.
- On failure: print a concise error to stderr and exit non-zero.

**Non-behavior:**
- Must not call `step()`.
- Must not create iteration directories directly (engine does this when entering `GENERATING`).

### 2.2 `aiwf step <session_id>`
**Purpose:** Advance the workflow by **one** deterministic engine unit-of-work.

**Inputs:**
- positional: `session_id`

**Behavior:**
- Calls `WorkflowOrchestrator.step(session_id)` exactly once.
- Prints a compact result summary:
  - phase/status after the call
  - whether the call advanced or was a no-op due to “awaiting artifact”
  - path(s) to relevant prompt/response artifacts when awaiting user input (manual workflow UX)

**Exit codes (recommended):**
- `0` if phase advanced OR prompt was issued
- `2` if no-op due to awaiting artifact (useful for scripts)
- `1` on error/exception
- `3` on user cancel

*(If you prefer different codes, lock them now; keep stable.)*

### 2.3 `aiwf status <session_id>`
**Purpose:** Show current workflow state and what the user should do next.

**Inputs:**
- positional: `session_id`

**Behavior:**
- Loads state via SessionStore (via orchestrator or directly via store, per existing design).
- Prints:
  - phase/status
  - current iteration (if any)
  - session path
  - “next action” guidance for manual mode:
    - if awaiting response: the expected response path to create
    - if prompt missing: the prompt path that will be created on next `step()`
    - if terminal: completion/error/cancelled summary

---

## 3. CLI Design Constraints

### 3.1 Thin CLI Rule
- CLI must be a pure application/UI layer.
- All workflow decisions remain in the engine.
- CLI must not inspect profile internals beyond selecting a profile key.

### 3.2 Output Rules
- Prefer single-line machine-readable outputs where applicable:
  - `init` prints only `session_id` on success.
- Human-friendly formatting is allowed for `status` and `step`, but keep it stable and parsable.

### 3.3 Error Handling
- Catch and render user-facing errors with minimal noise.
- Avoid stack traces by default; add `--debug` to show tracebacks (optional).

---

## 4. File/Module Targets (verify against repo)

Primary:
- `aiwf/cli.py` (new or existing)
- `aiwf/__main__.py` or console script entry (ensure `aiwf` runs)

Likely reused:
- `aiwf/application/workflow_orchestrator.py`
- `aiwf/domain/persistence/session_store.py`
- `aiwf/domain/models/workflow_state.py`

---

## 5. Test Strategy (M6)

### 5.1 Core Testing Principle
- Use **Click’s testing runner** (`click.testing.CliRunner`) for CLI unit tests.
- Do not mock engine internals unless necessary; prefer a temp directory and real SessionStore to ensure CLI wiring is correct.

### 5.2 New Test Location
- `tests/unit/cli/` (recommended)
  - `test_cli_init.py`
  - `test_cli_step.py`
  - `test_cli_status.py`

### 5.3 Minimum Assertions
- `init`:
  - exit code 0
  - stdout contains only the session_id
  - session exists on disk/persistence

- `step`:
  - when phase requires prompt issuance: prompt file exists after call, exit code 0
  - when awaiting response: exit code 2 and message indicates expected response path
  - when terminal: exit code 0 and message indicates terminal state

- `status`:
  - prints phase/status and paths
  - does not mutate state

---

## 6. M6 TDD Slices (Incremental)

### Slice A — CLI scaffold + entrypoint
- Add `aiwf/cli.py` with a Click group: `aiwf`.
- Ensure `python -m aiwf` and/or installed console script works.
- Add CLI test proving command group loads.

### Slice B — `aiwf init`
- Implement `init` command calling `WorkflowOrchestrator.initialize_run`.
- Test: returns session_id; session persisted; stable output.

### Slice C — `aiwf step`
- Implement `step <session_id>` command calling orchestrator once.
- Test: one call issues prompt / advances; output includes new phase/status.
- Test: returns exit code `2` on no-op due to awaiting artifact.

### Slice D — `aiwf status`
- Implement status view.
- Test: prints current phase/status and session path; does not mutate state.

### Slice E — CLI polish for manual workflows (optional but high value)
- Add consistent “next action” messaging (paths to prompt/expected response).
- Add `--json` output mode (optional; only if clearly beneficial).

---

## 7. Pydantic Validation (post‑M5 decision)

### 7.1 Recommended Milestone Placement
- **M6.1 (optional)**: Add Pydantic validation only at the persistence boundary (load/deserialize), without altering orchestrator semantics.
- **M7**: If broader schema/versioning is needed, handle migrations and compatibility.

### 7.2 M6 Default
- Do not adopt Pydantic in M6 core unless you explicitly decide that CLI must refuse to operate on invalid persisted state.

---

## 8. Acceptance Criteria for M6

M6 is complete when:
1. `aiwf init`, `aiwf step`, `aiwf status` exist and are tested.
2. Commands are thin wrappers; engine remains the only orchestrator.
3. Exit codes are stable and documented.
4. Manual workflow UX is supported by printing where to find/create artifacts.
5. No changes were required to profile code or engine semantics.

---

## 9. Immediate Next Action

Start with **Slice A** (CLI scaffold) using TDD, then proceed sequentially through `init`, `step`, `status`.

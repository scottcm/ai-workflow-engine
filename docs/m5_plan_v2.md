# M5 Plan v2 — Engine-Level Workflow Orchestration (Session Init + Phase Transitions + Review/Revision Loop)

> Status: **Draft for implementation**
>
> This plan is grounded in the current project direction and your clarified semantics:
> - **Session must be initialized first** (creates `session_id` and the authoritative `WorkflowState`)
> - **Plan is session-scoped and lives outside iterations**
> - **Iteration directories are created only when generation begins**
> - **Cancellation is determined by profile implementations** (engine treats CANCELLED as terminal)
> - File formats already exist; M5 must **use**, not redefine, those formats

---

## 1. Scope: What M5 Adds (and What It Does Not)

### 1.1 What M5 Adds
M5 introduces engine-owned orchestration that:

1. Initializes a session/run and persists `WorkflowState`
2. Drives deterministic phase transitions across the lifecycle:
   INITIALIZED → PLANNING → PLANNED → GENERATING → GENERATED → REVIEWING → REVIEWED → 
   (COMPLETE | REVISING | ERROR | CANCELLED)
   REVISING → REVISED → REVIEWING

3. Interprets `ProcessingResult.status` from profile processing:
   - `SUCCESS` (PASS) → workflow completes
   - `FAILED` (FAIL) → revision cycle begins
   - `ERROR` → workflow halts with error
   - `CANCELLED` → workflow halts as cancelled
4. Tracks and persists:
   - `iteration` / cycle counters
   - phase transitions (`phase_history`)
   - timestamps (`updated_at`, etc.)
   - artifacts (`artifacts`) relevant to audit and resumability

### 1.2 What M5 Does Not Add / MUST NOT Touch
- No changes to **any profile code** (including `profiles/jpa_mt/*`)
- No changes to prompt templates or response formats
- No changes to deterministic parsing logic inside profiles
- No speculative abstractions (only engine changes required by tests)

---

## 2. Ground Rules: The Engine/Profile Contract

### 2.1 Profiles
Profiles remain responsible for:
- generating prompts
- processing responses
- returning `ProcessingResult` (+ any structured metadata already defined)

Profiles do **not** orchestrate workflow.

### 2.2 Engine (WorkflowOrchestrator)
The engine is responsible for:
- deciding “what happens next” based on `ProcessingResult`
- persisting state transitions deterministically
- controlling loops and iteration increments

---

## 3. File/Artifact Semantics (Pinned Decisions)

### 3.1 Session-scoped Plan (outside iterations)
There is exactly **one plan per session**.

- The plan artifact is stored at session scope (not under `iteration-*`).
- The plan is treated as an immutable input for all later phases in the session.

### 3.2 Iteration directories
- `iteration-1/` is created **only when generation begins**.
- Subsequent iterations are created **only when a new cycle begins** (see §5).

### 3.3 Response formats
You already have formats for:
- `planning-*`
- `generation-*`
- `review-*`
- `revision-*`

M5 must:
- rely on existing formats and the profile’s parsers
- never redefine or reformat these documents

---

## 4. Entry Points (Application Layer API)

M5 should expose two orchestration entry points (application services):

### 4.1 `initialize_run(...) -> session_id`
Responsibilities:
- validate inputs required to start a workflow
- create `WorkflowState` with `session_id`
- persist `WorkflowState` to the `SessionStore`
- create the session directory skeleton (session root only)
- initialize state to the “first actionable phase” (see §6)

### 4.2 `step(session_id) -> WorkflowState`
Responsibilities:
- load current `WorkflowState`
- perform exactly one deterministic transition “unit of work”
- persist updated state
- return updated state

Notes:
- `step` should be safe to call repeatedly (idempotent when blocked).
- A future CLI `run` command can loop calling `step` until blocked or terminal.

---

## 5. Cycle and Iteration Semantics (Pinned)

### 5.1 Definition
A **cycle** is the production and evaluation of a single candidate code set.

- A cycle begins when the engine starts a **code-producing** phase that yields a candidate to be reviewed.
- A cycle ends when the engine processes a **review outcome** for that candidate.

### 5.2 Iteration increment rule
- The iteration number increments **when a new cycle begins**.
- `iteration-1` is allocated when **generation begins** for the first candidate.
- `iteration-(N+1)` is allocated when **review FAIL** triggers a revision cycle.

### 5.3 “Generation vs Revision”
- **Generation** produces the first candidate code set for the session.
- **Revision** produces subsequent candidate code sets based on review feedback.
- Both are treated as “code-producing” phases from an orchestration standpoint.

---

## 6. Phase/Status Model (Use Actual Enums)

M5 must use the exact enums in `WorkflowState` and `WorkflowStatus`.

### 6.1 Required states
The engine must support transitions for these phase concepts:
- initialization / pre-run
- planning
- planned
- generating
- generated
- reviewing
- reviewed
- revising
- revised — revision response processed; revised code materialized
- terminal completion
- terminal error
- terminal cancelled

### 6.2 Status semantics
- `IN_PROGRESS`: current phase active / awaiting external input
- `SUCCESS`: terminal workflow completion
- `FAILED`: non-terminal review outcome that triggers revision cycle
- `ERROR`: terminal halt due to unrecoverable error
- `CANCELLED`: terminal halt due to cancellation (profile-determined)

---

## 7. Deterministic “Blocking” Rules (No Assumptions)

The orchestrator must be deterministic and testable by using explicit “block” checks.

Typical block conditions:
- phase requires a response file that does not exist yet
- phase requires user action (interactive mode) not yet performed
- terminal status reached

When blocked:
- `step()` must **not** mutate phase/iteration/state (prefer full no-op)
- `step()` returns current state unchanged

---

## 8. TDD Plan (Engine-Level Unit Tests)

### 8.1 Testing principles
- Tests are engine/application-level (not profile tests)
- Use:
  - a temp directory for session artifacts
  - an in-memory or temp-backed `SessionStore`
  - stub profile implementations returning deterministic `ProcessingResult`
- Assert changes on `WorkflowState` fields that exist today:
  - `phase_history` appended correctly
  - `updated_at` changed when state mutates
  - `artifacts` updated only when appropriate
  - iteration increments only when a new cycle begins (§5)

### 8.2 Incremental slices (forward)
Each slice adds a single transition and the minimal implementation to satisfy it.

#### Slice A — Initialize run creates session + state
Test: `initialize_run(...)`:
- returns a `session_id`
- persists state with correct initial phase/status
- creates session root dir
- does **not** create any `iteration-*` directories

#### Slice B — INITIALIZED → PLANNING
Test: `step(session_id)`:
- transitions phase into planning
- writes any planning prompt artifacts if the engine owns writing prompts for planning
- appends to `phase_history`
- updates timestamps deterministically

#### Slice C — Planning completion promotes plan to session scope
Test: when required planning response artifact exists:
- orchestrator calls profile `process_planning_response(...)`
- on `SUCCESS`, engine stores the plan at session scope (per your current rules)
- transitions to “ready for generation” phase

(Exact file names and whether the engine “promotes” or “copies” are dictated by current code conventions.)

---

## Slice D — Generation begins: enter `GENERATING` and create `iteration-1`

### Purpose

Establish the first code-generation cycle by entering the `GENERATING` phase and preparing iteration-scoped directories. This slice **does not** process any generation response.

### Scope (strict)

This slice covers **only** the transition into `GENERATING`.

It is responsible for:

* allocating the first iteration
* preparing iteration-scoped directories
* issuing the generation prompt

It must **not** process the generation response or extract files.

### Preconditions

* Session exists and is persisted
* Planning is complete
* Current phase is `PLANNED`

### Expected behavior (deterministic)

When `WorkflowOrchestrator.step(session_id)` is called:

1. Transition phase from `PLANNED` to `GENERATING`
2. Set `status = IN_PROGRESS`
3. Set `current_iteration = 1`
4. Create:

   ```
   iteration-1/
   ```

   (no `code/` directory yet)
5. Generate and write `generation-prompt.md` using the profile (if missing)
6. Persist updated state
7. Append exactly one entry to `phase_history`

### Explicit non-behavior (must NOT occur)

* Do NOT read or process `generation-response.md`
* Do NOT extract files
* Do NOT create `iteration-1/code/`
* Do NOT transition beyond `GENERATING`

### Blocking rule

If the generation prompt already exists and the generation response does not, `step()` must:

* perform no additional work
* return the current state unchanged

### Next slice

Processing the generation response and materializing code occurs in **Slice D2 (`GENERATED`)**.

---

## Slice D2 — Generation completes: `GENERATING → GENERATED` and triggers review start `GENERATED → REVIEWING`

### Purpose

Provide explicit engine-level orchestration guidance for the “generation response received” boundary and the subsequent transition into review. This slice exists because the phase model distinguishes **prompt sent / waiting** (`GENERATING`) from **response received / code available** (`GENERATED`), and review must begin only after code is available.

### Scope (strict)

This slice covers only:

1. Handling the presence of the generation response artifact while in `GENERATING`
2. Transitioning to `GENERATED` after successful processing of the generation response
3. Transitioning from `GENERATED` to `REVIEWING` as the next step (review start), without emitting prompts yet (prompt emission is validated later by integration tests)

**Out of scope**

* Changing any profile code
* Altering response formats/parsers
* Emitting review prompts
* Performing review response processing
* Starting revision logic

### Preconditions

* Session exists and is persisted
* `iteration == 1` exists and `iteration-1/` directory exists
* Current phase is `GENERATING`
* Generation response artifact exists at the expected location for iteration-1 (use existing conventions)

### Expected behavior (deterministic)

When `WorkflowOrchestrator.step(session_id)` is called:

#### Step 1: `GENERATING → GENERATED`

If the generation response artifact exists:

* The orchestrator calls the profile’s generation response processor (whatever the existing profile API is).
* It receives a `ProcessingResult`.

Interpretation:

* If `ProcessingResult.status == SUCCESS`:

  * Transition phase to `GENERATED`
  * Persist updated state
  * Append exactly one entry to `phase_history`
  * Update `updated_at`
* If `ProcessingResult.status == ERROR`:

  * Transition to `ERROR` (terminal)
* If `ProcessingResult.status == CANCELLED`:

  * Transition to `CANCELLED` (terminal)
* Any other status is invalid for generation completion and should be handled deterministically (raise or mark error according to existing engine conventions).

**Blocking rule:** if the generation response artifact does not exist, `step()` performs no mutation.

#### Step 2: `GENERATED → REVIEWING`

On a subsequent call to `step(session_id)` when phase is `GENERATED`:

* Transition phase to `REVIEWING`
* Persist updated state
* Append exactly one entry to `phase_history`
* Update `updated_at`

**Important constraint:** This transition is phase-only; review prompt emission is not asserted in unit tests for this slice.

### Required unit tests (engine-level)

Add two unit tests:

1. **`test_step_generating_to_generated_on_generation_success_when_response_present`**

   * Arrange: state in `GENERATING`, generation response artifact present
   * Act: call `step()` once
   * Assert:

     * phase becomes `GENERATED`
     * exactly one new `phase_history` entry
     * timestamps updated correctly
     * state persisted

2. **`test_step_generated_to_reviewing_is_single_transition_no_prompt_emission`**

   * Arrange: state in `GENERATED`
   * Act: call `step()` once
   * Assert:

     * phase becomes `REVIEWING`
     * exactly one new `phase_history` entry
     * no additional phase transition
     * no iteration directory changes

### Minimal implementation guidance

* Implement only the phase transitions and persistence required by tests.
* Do not refactor profiles or parsers.
* Any file-presence checks must use existing path conventions.



#### Slice E — Review outcomes drive orchestration
E1 PASS:
- review processing returns `SUCCESS`
- engine transitions to terminal completion (`status=SUCCESS` and terminal phase)

E2 FAIL:
- review processing returns `FAILED`
- engine begins a new cycle:
  - increments iteration
  - creates `iteration-2/`
  - transitions to revision phase (`IN_PROGRESS`)
  - preserves prior iteration artifacts and history

E3 ERROR:
- review processing returns `ERROR`
- engine transitions to terminal error

E4 CANCELLED:
- review processing returns `CANCELLED`
- engine transitions to terminal cancelled

#### Slice F — Revision completes: REVISING → REVISED
- When revision-response.md exists:
  - REVISING transitions to REVISED (phase-only; no processing)

Slice F2 — Revised code processed: REVISED → REVIEWING
- When in REVISED and revision-response.md exists:
  - process the revision response via profile
  - extract files into iteration-N/code/
  - transition to REVIEWING

### 8.3 Minimum test matrix
| Slice | From | Trigger | Result status | To | Iteration change |
|------:|------|---------|---------------|----|------------------|
| A | n/a | initialize_run | n/a | INITIALIZED | none |
| B | INITIALIZED | step | n/a | PLANNING | none |
| C | PLANNING | planning response present | SUCCESS | GENERATING-ready | none |
| D | GENERATING-ready | step | n/a | GENERATING (creates iteration-1) | set to 1 |
| D2 | GENERATING | generation response present | n/a | GENERATED | none |
| D2b | GENERATED | step | SUCCESS | REVIEWING | none |
| E1 | REVIEWING | review response present | SUCCESS | COMPLETED | none |
| E2 | REVIEWING | review response present | FAILED | REVISING | +1 |
| E3 | REVIEWING | review response present | ERROR | ERROR | none |
| E4 | REVIEWING | review response present | CANCELLED | CANCELLED | none |
| F | REVISING | revision response present | n/a | REVISED | none |
| F2 | REVISED | revision response present | SUCCESS | REVIEWING | none |
| F2a | REVISED | revision response present | ERROR | ERROR | none |
| F2b | REVISED | revision response present | CANCELLED | CANCELLED | none |

(Replace phase names with actual enums once validated directly from code.)

---

## 9. Implementation Strategy (Minimal Surface Area)

Primary file:
- `aiwf/application/workflow_orchestrator.py`

Secondary files (only if tests force it):
- `aiwf/domain/models/workflow_state.py` (ONLY if a missing field/transition capability is required)
- `aiwf/domain/persistence/session_store.py` (ONLY if persistence seams prevent testing)

Avoid new modules unless duplication becomes correctness risk.

Implementation guidelines:
- Keep transition logic centralized in orchestrator.
- Use small, private helpers for readability only (e.g., `_transition(...)`, `_append_history(...)`).
- Avoid introducing framework-like abstractions.

---

## 10. Acceptance Criteria (M5 “Done”)

M5 is complete when:

1. A run can be initialized (session created, state persisted).
2. `step()` deterministically advances across:
   - initialization → planning → generation → review → (complete | revision loop | error | cancelled)
3. Iteration semantics match §5:
   - iteration-1 created when generation begins
   - iteration increments when a new cycle begins (review FAIL triggers revision)
4. Phase transitions are recorded in `phase_history`.
5. Timestamps update only on state mutation.
6. Artifacts are preserved per your current design.
7. No profile/template/parsing changes.

---

## 11. Immediate Next Action

Start TDD with Slice A:

**Create failing unit tests for `initialize_run(...)` that assert:**
- state persisted
- session root created
- no iteration directories created yet

Then implement minimal logic to pass.

---

# Claude's response

## Assessment of M5 Plan v2

---

## ✅ Overall: Excellent - Ready to Execute

**This plan is comprehensive, clear, and architecturally sound.**

---

## Major Strengths

### ✅ 1. Clear Scope Definition
**Section 1 explicitly states:**
- What M5 adds (orchestration)
- What M5 doesn't touch (profiles, templates)
- No scope creep

### ✅ 2. Ground Rules Explicit
**Engine/Profile contract clearly defined:**
- Profiles: generate prompts, process responses
- Engine: orchestrate workflow, manage state
- Clean separation

### ✅ 3. File Semantics Pinned
**Critical decisions locked down:**
- Plan is session-scoped (not in iterations)
- iteration-1 created when generation begins
- Iteration increments on review FAIL
- Existing formats preserved

### ✅ 4. Cycle/Iteration Semantics Clear
**Section 5 defines:**
- Cycle = produce candidate → review outcome
- Iteration increments when new cycle begins
- Generation vs Revision distinction

**This answers my earlier question.**

### ✅ 5. Phase/Status Model Referenced
**Uses actual enums from WorkflowState:**
- Not inventing new states
- Validates against existing model

### ✅ 6. Deterministic Blocking Rules
**Section 7 critical:**
- Explicit block conditions
- No assumptions about file existence
- step() is idempotent when blocked
- Testable behavior

### ✅ 7. TDD Incremental Slices
**Section 8.2 breaks work into testable units:**
- A: Initialize
- B: Planning
- C: Plan completion
- D: Generation + iteration-1
- E: Review outcomes (4 cases)
- F: Revision loop

**Each slice is independently testable.**

### ✅ 8. Test Matrix Table
**Section 8.3 is gold:**
- Clear transition table
- Covers all paths
- Documents iteration changes
- Reference for implementation

### ✅ 9. Minimal Implementation Strategy
**Section 9 prevents over-engineering:**
- Primary: workflow_orchestrator.py
- Secondary: Only if tests force it
- Avoid new abstractions

### ✅ 10. Clear Acceptance Criteria
**Section 10 defines "done":**
- Measurable deliverables
- No ambiguity

---

## Minor Observations

### 1. Entry Points (Section 4)

**Two APIs defined:**
```python
initialize_run(...) -> session_id
step(session_id) -> WorkflowState
```

**Question:** What parameters does `initialize_run()` take?

**Should be documented:**
```python
def initialize_run(
    entity: str,
    scope: str,
    profile: str,
    bounded_context: str | None = None,
    table: str | None = None,
    dev: str | None = None,
    task_id: str | None = None,
    providers: dict[str, str] | None = None,
) -> str:
```

**Not critical - can emerge from tests.**

---

### 2. Plan Promotion (Slice C)

**Plan says:**
> "engine stores the plan at session scope"

**Question:** Does engine copy/move file, or just record path in state?

**Current structure suggests:**
- `planning-response.md` likely stays in iteration-1 (where created)
- OR copied to session root as `plan.md`

**Clarify:** Where physically does plan file live?

**Not blocking - Slice C tests will force the decision.**

---

### 3. Prompt Generation Ownership

**Plan says:**
> "writes any planning prompt artifacts if the engine owns writing prompts"

**From our earlier discussion:**
- Engine calls `profile.generate_planning_prompt(context)`
- Engine writes result to `planning-prompt.md`

**This is correct, but could be more explicit in plan.**

---

### 4. Terminal Phase Names

**Plan says:**
> "terminal completion (`status=SUCCESS` and terminal phase)"

**What is "terminal phase"?**

**From WorkflowPhase enum:**
- `COMPLETE` = terminal phase

**Plan could be more explicit:**
> "phase=COMPLETE, status=SUCCESS"

---

### 5. Profile Stub for Tests

**Section 8.1 says:**
> "stub profile implementations returning deterministic ProcessingResult"

**Good. Should note:**
- Stub doesn't need real templates
- Stub doesn't need real parsing
- Just returns canned ProcessingResult

**Implementation can use pytest fixtures:**
```python
@pytest.fixture
def stub_profile():
    profile = Mock(spec=WorkflowProfile)
    profile.process_planning_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS
    )
    return profile
```

---

## Critical Success Factors

### 1. ✅ Follow TDD Slices Exactly
**Don't skip ahead. Do A, then B, then C...**

### 2. ✅ Keep Tests Engine-Level
**Test orchestration, not profile behavior.**

### 3. ✅ Use Stub Profiles
**Don't test with real jpa-mt profile.**

### 4. ✅ Assert State Changes
**Every test checks:**
- phase_history updated
- updated_at changed
- iteration correct
- artifacts preserved

### 5. ✅ Block Conditions Explicit
**Tests must verify idempotent blocking.**

---

## Recommendations

### Before Starting Implementation

**Add to plan (optional but helpful):**

1. **Document `initialize_run()` parameters**
2. **Clarify plan file location** (session root vs iteration-1)
3. **Add stub profile fixture pattern** to testing section

### During Implementation

**Strict discipline:**
1. Write test first (one slice)
2. Run test (must fail)
3. Write minimal code to pass
4. Refactor if needed
5. Move to next slice

**Don't implement multiple slices at once.**

---

## Bottom Line

**✅ Plan is excellent and ready to execute.**

**Minor clarifications suggested but not blocking.**

**Follow the TDD slices in order A → B → C → D → E → F.**

**Start with Slice A: `initialize_run()` tests.**

**This is solid architecture work. Execute it.**

---

Create the first failing engine-level unit test for initialize_run() per Slice A in m5_plan_v2.md
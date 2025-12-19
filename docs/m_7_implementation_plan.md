# M7 Implementation Plan

This document defines the full implementation plan for M7, broken into discrete, test-driven slices. Each slice is independently verifiable and builds on locked contracts from prior slices.

---

## Slice 1 — Core Domain Model Contracts

**Goal**: Lock all domain-level contracts required by M7.

**Scope**:
- Artifact (metadata-only, strict)
- WorkflowState (hashing + approval surface)
- WriteOp / WritePlan
- ProcessingResult

**Outcomes**:
- Stable public model surface
- No legacy aliasing or type semantics
- Profiles and engine can rely on fixed contracts

---

## Slice 2 — Engine Execution of WritePlan

**Goal**: Make the engine responsible for executing WritePlan objects.

**Scope**:
- Engine writes files described by WritePlan
- Compute SHA-256 hashes at write time
- Create Artifact metadata per write
- Append artifacts to WorkflowState

**Outcomes**:
- Profiles remain pure (no I/O)
- Deterministic file materialization

---

## Slice 3 — Standards Bundle Materialization

**Goal**: Materialize standards bundles as session-scoped files.

**Scope**:
- Load standards content from configured sources
- Concatenate into a single standards bundle
- Write bundle to session directory
- Compute and store standards hash

**Outcomes**:
- Standards become file-materialized inputs
- Hashing enables approval semantics

---

## Slice 4 — Plan Approval and Hash Locking

**Goal**: Introduce explicit plan approval semantics.

**Scope**:
- Compute plan hash
- Record plan approval in WorkflowState
- Warn (non-blocking) on hash mismatch

**Outcomes**:
- Approval becomes a first-class workflow step
- Hashes support safe re-execution

---

## Slice 5 — Review and Revision Write Plans

**Goal**: Extend WritePlan usage to review and revision phases.

**Scope**:
- Review phase produces WritePlan
- Revision phase produces WritePlan
- Engine executes plans consistently

**Outcomes**:
- Uniform artifact handling across phases
- Cleaner phase symmetry

---

## Slice 6 — Artifact-Gated Engine Advancement

**Goal**: Enforce artifact presence before phase transitions.

**Scope**:
- Engine checks required artifacts exist
- No-op behavior when awaiting artifacts

**Outcomes**:
- Deterministic gating
- Manual workflows remain first-class

---

## Slice 7 — Iteration-Aware Artifact Handling

**Goal**: Ensure artifact paths and metadata are iteration-aware.

**Scope**:
- Iteration-specific directories
- Artifact metadata records iteration

**Outcomes**:
- Clear separation of iterations
- Safe revision loops

---

## Slice 8 — Engine-Level Hash Comparison and Warnings

**Goal**: Surface hash mismatches without blocking execution.

**Scope**:
- Compare current vs stored hashes
- Emit warnings only

**Outcomes**:
- User visibility into stale inputs
- Non-enforcing safety checks

---

## Slice 9 — Session Persistence Integration

**Goal**: Persist updated WorkflowState after each step.

**Scope**:
- Save state after WritePlan execution
- Reload state consistently

**Outcomes**:
- Reliable resume behavior
- Clear state transitions

---

## Slice 10 — CLI Exposure of Approval and Hash State

**Goal**: Surface approval and hash info in CLI output.

**Scope**:
- CLI status shows approval state
- CLI step reports warnings

**Outcomes**:
- Transparency for users
- Scriptable inspection

---

## Slice 11 — Programmatic API Consumption

**Goal**: Make M7 workflows consumable via structured output.

**Scope**:
- JSON output includes artifacts, hashes, approvals

**Outcomes**:
- IDE and automation integration ready

---

## Slice 12 — Cross-Profile Consistency Validation

**Goal**: Ensure all profiles conform to M7 contracts.

**Scope**:
- Validate WritePlan usage across profiles
- Detect non-conforming behavior

**Outcomes**:
- Predictable profile behavior
n
---

## Slice 13 — Hardening and Invariants

**Goal**: Lock invariants and remove deprecated paths.

**Scope**:
- Remove dead legacy code
- Assert invariants via tests

**Outcomes**:
- Stable M7 foundation
- Reduced maintenance risk

---

## Completion Criteria

M7 is complete when:
- All slices pass their tests
- No domain contracts change post-Slice 1
- Engine owns all file materialization
- Profiles are pure and deterministic
- Manual and automated workflows behave identically

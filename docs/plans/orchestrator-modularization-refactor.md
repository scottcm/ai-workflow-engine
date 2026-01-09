# WorkflowOrchestrator Modularization Plan

Goal: reduce monolithic responsibilities in `aiwf/application/workflow_orchestrator.py` (1,399 lines) by extracting focused services and action executors while preserving existing behavior.

Scope: orchestration, action execution, approval gating, provider execution, prompt assembly, artifact hashing, and file I/O boundaries.

Non-goals:
- Behavior changes in workflow state machine or approval semantics.
- Provider contract changes.
- Profile API changes.

Success criteria:
- Orchestrator coordinates only; no direct file I/O or approval/provider branching.
- Each action is testable in isolation.
- Approval gating logic lives in a single service.
- Provider execution is centralized and capability-aware.
- Regression tests pass with minimal rewrites.

## Success Metrics

| Metric | Target | Type | Rationale |
|--------|--------|------|-----------|
| Orchestrator line count | < 400 lines | Guideline | Currently 1,399; coordination-only should be ~30% |
| Service line count | < 200 lines each | Guideline | Single responsibility |
| Service dependencies | <= 2 other services | Guideline | Avoid tight coupling |
| Responsibility boundaries | Clear | **Hard gate** | Each service owns one concern |
| Test isolation | Services testable alone | **Hard gate** | No orchestrator needed to test service |
| Test rewrites | < 20% of existing | Guideline | Behavior unchanged |

## Decisions

**D1: run_provider migration**
Keep `approval_handler.run_provider()` as deprecated shim until Phase 3. Update call sites/tests to use `ProviderExecutionService` during Phase 3, then remove shim in follow-up cleanup PR. Avoids breaking tests and reduces refactor risk.

**D2: Line count targets**
Treat line counts as guidelines, not hard gates. The stronger success criteria are responsibility boundaries and test isolation. Track branching/complexity or public method count instead of strict LOC.

---

## Pre-Work (before Phase 0)

Quick wins to reduce noise before refactor:

- [ ] Update `API-CONTRACT.md` - remove `step` command documentation (10 min)
- [ ] Mark `approval_handler.py` as deprecated (per D1):
  - Add deprecation warning to `run_provider()`
  - Tests continue to work; migration happens in Phase 3
- [ ] Update ADR-0013/0014 status from "Draft" to "Accepted" (5 min)

---

## Phase 0: Safety Net

### Existing Coverage Analysis

**Already well-covered** (63 tests across 3 files):

| File | Tests | Coverage |
|------|-------|----------|
| `test_behavioral_contracts.py` | 19 | Gate decisions, retry, context builders, error recovery |
| `test_orchestrator_transitions.py` | 24 | State transitions, command validation, auto-continue |
| `test_approval_flow.py` (integration) | 13 | Full approval scenarios, mixed configs |

### Gaps Requiring New Tests

The following behaviors are critical to the refactor and need explicit coverage:

#### 1. Retry Loop Edge Cases

```
Location: _handle_response_rejection (lines 1230-1285)

Tests needed:
- [ ] Retry succeeds on attempt 2 of 3 -> returns None, workflow continues
- [ ] Retry succeeds on final attempt -> returns None, workflow continues
- [ ] max_retries=0 -> no retry loop, immediate pause
- [ ] PENDING during retry loop -> pauses, preserves retry_count
```

#### 2. Review Verdict Transitions

```
Location: _action_check_verdict (lines 490-530)

Tests needed:
- [ ] Verdict PASS -> phase=COMPLETE, stage=None, status=SUCCESS
- [ ] Verdict FAIL -> iteration++, phase=REVISE, stage=PROMPT, creates prompt
- [ ] Invalid verdict -> last_error set, workflow continues (not blocked)
- [ ] Missing verdict -> same as invalid
```

#### 3. Prompt Rejection with Regeneration

```
Location: _handle_prompt_rejection, _try_prompt_regeneration (lines 1146-1228)

Tests needed:
- [ ] Profile with can_regenerate_prompts=True -> regeneration attempted
- [ ] Regeneration succeeds -> gate re-runs, may auto-continue
- [ ] Regeneration raises NotImplementedError -> falls through to user pause
- [ ] Regeneration rejected again -> recurses (verify no infinite loop)
```

#### 4. State Mutation Timing (ADR-0012)

```
Location: _auto_continue (lines 1047-1083)

Tests needed:
- [ ] State updates BEFORE action execution (phase/stage set first)
- [ ] Terminal state detection after transition (COMPLETE/CANCELLED/ERROR)
- [ ] Action failure after transition -> state already updated
```

#### 5. Approval File Collection

```
Location: _build_approval_files (lines 922-975)

Tests needed:
- [ ] PROMPT stage -> only prompt file in dict
- [ ] RESPONSE stage -> response file + code files if exist
- [ ] GENERATE/REVIEW phases -> includes plan.md
- [ ] Missing files -> None values in dict (not KeyError)
```

### Test Implementation Plan

Create new file: `tests/unit/application/test_orchestrator_refactor_safety.py`

Purpose: Explicit tests for behaviors being extracted. These tests:
1. Document expected behavior before refactor
2. Catch regressions during extraction
3. Can be moved to service-specific test files after extraction

Estimated: 15-20 new tests, ~400 lines

---

## Phased Refactor Plan

### Phase 1: Action Executors (lowest risk extraction)

1. Create `ActionExecutor` protocol and `ActionDispatcher`.
2. Move `_action_create_prompt`, `_action_call_ai`, `_action_check_verdict`, `_action_finalize`, `_action_cancel` into executor classes.
3. Orchestrator delegates to dispatcher in `_execute_action`.
4. Keep file I/O in executors for now.

**Checkpoint:** All tests pass. Orchestrator reduced by ~150 lines.

### Phase 2: ApprovalGateService (isolate gating)

1. Extract `_run_gate_after_action` and related helpers into `ApprovalGateService`.
   - `_build_approval_files`
   - `_build_approval_context`
   - `_handle_approval_rejection`, `_handle_prompt_rejection`, `_handle_response_rejection`
   - `_try_prompt_regeneration`, `_apply_suggested_content_to_prompt`
2. Orchestrator calls `approval_gate_service.run_after_action(...)`.
3. Preserve existing state mutations and messages.

**Checkpoint:** All tests pass. Orchestrator reduced by ~300 lines. Gate logic testable in isolation.

**STOP GATE:** If approval tests fail or regress, stop and reassess before Phase 3.

### Phase 3: ProviderExecutionService (centralize provider calls)

1. Extract provider lookup, metadata usage, timeouts, and response handling.
2. Normalize results into `ProviderExecutionResult`:
   - response written vs returned
   - files written vs returned
3. Action executor `CallAIAction` uses the service.
4. Migrate `approval_handler.run_provider()` callers to use service, then delete module.

**Checkpoint:** All tests pass. Provider logic centralized. `approval_handler.py` deleted.

**STOP GATE:** If provider tests regress, stop and reassess.

### Phase 4: PromptService (centralize prompt assembly)

Note: `PromptAssembler` already exists. This phase extracts the *calling* logic:
- profile prompt generation dispatch
- response path calculation
- assembler invocation

Action executor `CreatePromptAction` uses the service.

**Checkpoint:** All tests pass. Prompt logic centralized.

### Phase 5: ArtifactService (hashing and artifact updates)

Extract the pre-transition approval handlers that own hashing and artifact creation:

1. Extract `_handle_pre_transition_approval` dispatcher (lines 688-701)
2. Extract `_approve_*` methods (~140 lines total):
   - `_approve_plan_response` - hashes planning-response.md, sets plan_approved
   - `_approve_generate_response` - extracts code, creates artifacts
   - `_approve_review_response` - hashes review-response.md, sets review_approved
   - `_approve_revise_response` - extracts revised code, creates artifacts
3. Extract `_copy_plan_to_session` helper
4. Move `_APPROVAL_HANDLERS` dispatch table to service

**Checkpoint:** All tests pass. Hashing/artifact logic isolated and testable.

### Phase 6: SessionFileGateway (centralize file I/O)

1. Introduce gateway for prompt/response/code reads and writes.
2. Replace direct `Path` usage in executors and services with gateway calls.

**Checkpoint:** All tests pass. No direct Path operations in orchestrator.

---

## Proposed Architecture

New services/modules:
- `aiwf/application/actions/` (action executors)
- `aiwf/application/approval/approval_gate_service.py`
- `aiwf/application/providers/provider_execution_service.py`
- `aiwf/application/prompts/prompt_service.py`
- `aiwf/application/artifacts/artifact_service.py`
- `aiwf/application/storage/session_file_gateway.py`

Orchestrator becomes a coordinator/facade:
- reads/writes `WorkflowState`
- consults TransitionTable
- dispatches actions
- invokes approval gate after actions

Design patterns:
- Command: per-action executors
- Strategy: providers and approvers (already); add action executor strategy
- Facade: orchestrator as coordinator
- Repository/Gateway: session state vs file I/O
- Builder: prompt assembly is a builder service

---

## Risk and Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| Behavior drift in gating/retry flows | High | Phase 0 tests + explicit retry loop coverage |
| State mutation timing breaks | High | ADR-0012 timing tests |
| Infinite recursion in regeneration | Medium | Max depth or explicit test |
| Partial refactor abandonment | Medium | Checkpoints after each phase |
| Increased indirection complexity | Low | Clear interfaces, <= 200 lines per service |

---

## Deliverables Checklist

Pre-work:
- [ ] Update API-CONTRACT.md (remove step)
- [ ] Handle approval_handler.py (migrate or deprecate)
- [ ] Update ADR statuses

Phase 0:
- [ ] test_orchestrator_refactor_safety.py with 15-20 tests

Phases 1-6:
- [ ] Action executors and dispatcher
- [ ] Approval gate service with isolated tests
- [ ] Provider execution service (+ approval_handler.py deletion)
- [ ] Prompt service
- [ ] Artifact service (including _handle_pre_transition_approval extraction)
- [ ] Session file gateway
- [ ] Orchestrator reduced to coordination only (< 400 lines)

---

## Suggested Order for PRs

1. Pre-work: doc fixes + approval_handler migration decision
2. Phase 0: Safety net tests
3. Phase 1: Action executors + dispatcher
4. Phase 2: Approval gate service
5. Phase 3: Provider execution service + approval_handler.py deletion
6. Phase 4: Prompt service
7. Phase 5: Artifact service
8. Phase 6: Session file gateway
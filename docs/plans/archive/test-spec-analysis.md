# Test vs Spec Analysis: Approval System

**Date:** January 2026
**Scope:** ADR-0015 + Implementation Plan vs existing tests

---

## Summary

| Category | Count |
|----------|-------|
| Spec requirements extracted | 14 |
| Fully covered by spec tests | 10 |
| Partially covered | 2 |
| **Gaps (no spec test)** | 2 |
| Implementation-only tests | ~5 |

---

## Spec Requirements Mapping

### 1. Gate Ordering (gate before hash)

**Spec:** "Approval gate must evaluate and approve content before it becomes immutable."

| Test | File | Type |
|------|------|------|
| `test_approval_runs_before_hashing` | test_behavioral_contracts.py | **SPEC** |
| `test_rejection_does_not_set_plan_hash` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 2. retry_count Lifecycle

**Spec:** "`retry_count` resets to 0 on stage change."

| Test | File | Type |
|------|------|------|
| `test_retry_count_resets_on_stage_change` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

**Note:** The assertion `state.retry_count == 0` after success is a spec requirement per the Implementation Plan line 50: "Reset to 0 when stage changes".

---

### 3. Manual Approver Returns PENDING

**Spec:** "ManualApprovalProvider.evaluate() returns PENDING to signal pause."

| Test | File | Type |
|------|------|------|
| `test_evaluate_returns_pending` | test_manual_approver.py | **SPEC** |
| `test_manual_approver_returns_pending_for_all_phases` | test_manual_approver.py | **SPEC** |
| `test_manual_approver_returns_pending_pauses_workflow` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 4. Three-State Decisions

**Spec:** "APPROVED, REJECTED, PENDING clearly express all outcomes."

| Test | File | Type |
|------|------|------|
| `test_approval_decision_has_three_values` | test_approval_result.py | **SPEC** |
| `test_pending_decision_exists` | test_approval_result.py | **SPEC** |
| `test_pending_result_no_feedback_required` | test_approval_result.py | **SPEC** |

**Status:** Covered

---

### 5. Response Parsing (lenient with fallback)

**Spec:** Parse `DECISION:` line, keyword fallback, default to REJECTED.

| Test | File | Type |
|------|------|------|
| `test_ai_approver_returns_approved_on_approved_response` | test_ai_approver.py | **SPEC** |
| `test_ai_approver_returns_rejected_on_rejected_response` | test_ai_approver.py | **SPEC** |
| `test_ai_approver_case_insensitive_approved` | test_ai_approver.py | **SPEC** |
| `test_ai_approver_case_insensitive_rejected` | test_ai_approver.py | **SPEC** |
| `test_ai_approver_handles_ambiguous_response` | test_ai_approver.py | **SPEC** |
| `test_ai_approver_handles_empty_response` | test_ai_approver.py | **SPEC** |
| `test_malformed_response_defaults_to_rejection` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 6. suggested_content Handling

**Spec:** "Store in `state.suggested_content`, pass to provider in retry context."

| Test | File | Type |
|------|------|------|
| `test_suggested_content_stored_in_state` | test_behavioral_contracts.py | **SPEC** |
| `test_suggested_content_included_in_context_on_retry` | test_behavioral_contracts.py | **SPEC** |
| `test_ai_approver_extracts_suggested_content_when_allowed` | test_ai_approver.py | **SPEC** |
| `test_ai_approver_ignores_suggested_content_when_not_allowed` | test_ai_approver.py | **SPEC** |

**Status:** Covered

---

### 7. PROMPT Rejection Behavior

**Spec:** "Cannot auto-retry unless profile declares `can_regenerate_prompts`."

| Test | File | Type |
|------|------|------|
| `test_profile_without_regeneration_pauses_on_prompt_rejection` | test_behavioral_contracts.py | **SPEC** |
| `test_profile_with_regeneration_attempts_regeneration` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 8. max_retries Exhaustion

**Spec:** "Workflow remains IN_PROGRESS (not ERROR)."

| Test | File | Type |
|------|------|------|
| `test_max_retries_exceeded_stays_in_progress` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 9. Built-in Providers

**Spec:** "`skip` returns APPROVED, `manual` returns PENDING."

| Test | File | Type |
|------|------|------|
| `test_skip_approver_always_approves` | test_skip_approver.py | **SPEC** |
| `test_skip_approver_approves_all_phases_and_stages` | test_skip_approver.py | **SPEC** |
| (manual covered in #3 above) | | |

**Status:** Covered

---

### 10. Context Builder Pattern

**Spec:** "Base context with extension for approval-specific keys."

| Test | File | Type |
|------|------|------|
| `test_base_context_contains_shared_keys` | test_behavioral_contracts.py | **SPEC** |
| `test_approval_context_extends_base_context` | test_behavioral_contracts.py | **SPEC** |
| `test_provider_context_uses_base_context` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 11. Approval Error Handling

**Spec:** "Provider errors during approval keep workflow recoverable (IN_PROGRESS)."

| Test | File | Type |
|------|------|------|
| `test_provider_exception_keeps_workflow_in_progress` | test_behavioral_contracts.py | **SPEC** |
| `test_provider_timeout_keeps_workflow_in_progress` | test_behavioral_contracts.py | **SPEC** |

**Status:** Covered

---

### 12. REJECTED Requires Feedback

**Spec:** "Rejection must include feedback explaining why."

| Test | File | Type |
|------|------|------|
| `test_rejected_requires_feedback` | test_approval_result.py | **SPEC** |
| `test_rejected_empty_feedback_invalid` | test_approval_result.py | **SPEC** |
| `test_rejected_whitespace_feedback_invalid` | test_approval_result.py | **SPEC** |

**Status:** Covered

---

## GAPS: Missing Spec Tests

### GAP 1: fs_ability Validation

**Spec (line 336-343):** "Providers with `fs_ability='none'` cannot be used for approval."

**Current state:** No test validates this.

**Required test:**
```python
def test_approval_factory_rejects_none_fs_ability():
    """Factory should reject providers with fs_ability='none'."""
    # Mock a provider with fs_ability='none'
    # Attempt to create via ApprovalProviderFactory
    # Assert ValueError is raised
```

---

### GAP 2: Files/Context Contract per Gate

**Spec (lines 191-205):** Each gate receives specific files in the `files` dict.

| Gate | Expected files |
|------|----------------|
| PLAN[PROMPT] | `planning-prompt.md` |
| PLAN[RESPONSE] | `planning-prompt.md`, `planning-response.md` |
| GENERATE[RESPONSE] | `generation-prompt.md`, code files |
| etc. | |

**Current state:** No test validates that the orchestrator assembles the correct files per gate.

**Required tests:**
```python
class TestFilesContextPerGate:
    """Contract: Each gate receives specific files per spec."""

    def test_plan_prompt_gate_receives_correct_files(self):
        """PLAN[PROMPT] gate receives planning-prompt.md."""

    def test_plan_response_gate_receives_correct_files(self):
        """PLAN[RESPONSE] gate receives planning-prompt.md and planning-response.md."""

    # ... one per gate
```

---

## PARTIAL: Tests That Need Strengthening

### PARTIAL 1: pending_approval State Transitions

**Spec:** "PENDING sets `pending_approval=True`, `approve` clears it."

**Current tests:** `test_manual_approver_returns_pending_pauses_workflow` checks `pending_approval=True` is set.

**Missing:** No test explicitly validates that `approve()` clears `pending_approval`.

**Suggested addition:**
```python
def test_approve_clears_pending_approval(self):
    """approve() should set pending_approval=False."""
    state = _make_state(pending_approval=True, ...)
    orchestrator.approve("session-id")
    assert state.pending_approval is False
```

---

### PARTIAL 2: Gates Run Automatically After Content Creation

**Spec:** "Gates run immediately after content creation (CREATE_PROMPT, CALL_AI)."

**Current tests:** Tests call `_run_gate_after_action` directly but don't verify it's called from `_execute_action`.

**Missing:** Integration-level test that content creation triggers gate automatically.

---

## Implementation-Only Tests (Not Spec-Derived)

These tests validate implementation details, not spec requirements:

| Test | File | Concern |
|------|------|---------|
| `test_manual_approver_is_approval_provider` | test_manual_approver.py | Type hierarchy (impl detail) |
| `test_skip_approver_can_be_instantiated` | test_skip_approver.py | Constructor works (trivial) |
| `test_ai_approver_context_does_not_affect_parsing` | test_ai_approver.py | Negative assertion (impl detail) |
| `test_model_dump_*` | test_approval_result.py | Serialization details |

**Verdict:** These are fine to keep but shouldn't be considered "spec coverage."

---

## Recommendations

1. **Add GAP 1 test:** fs_ability validation in ApprovalProviderFactory
2. **Add GAP 2 tests:** Files/context contract per gate (12 tests, one per gate)
3. **Strengthen PARTIAL 1:** Add explicit `approve()` clears `pending_approval` test
4. **Strengthen PARTIAL 2:** Integration test for gate-after-creation

**Priority:** GAP 2 is highest priority - it's the contract most likely to break silently.

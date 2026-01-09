# Approval Gate Architecture Redesign

**Status:** DRAFT (v2)
**Related:** [ADR-0015 Specification](adr0015-approval-providers.md)
**Created:** January 3, 2026
**Revised:** January 3, 2026

---

## Problem Statement

The current `ManualApprovalProvider` implementation violates provider abstraction:

1. `ManualApprovalProvider.evaluate()` returns `None` but is **never called**
2. Engine uses `isinstance(approver, ManualApprovalProvider)` to bypass the gate entirely
3. Gates only run when user issues `approve` command, not when content is ready
4. This prevents fully automated workflows (AI approvers still need manual `approve` commands)

---

## Architectural Change

**Current:** Gates run when user issues `approve` command
```
Content created → workflow pauses → user issues approve → gate runs → result handled
```

**Proposed:** Gates run automatically after content creation
```
Content created → gate runs immediately → result determines next step
```

| Gate Result | Engine Behavior |
|-------------|-----------------|
| APPROVED | Auto-continue to next stage (no user command needed) |
| REJECTED | Handle rejection (retry, apply suggested_content, halt) |
| PENDING | Set `pending_approval=True`, save state, exit cleanly |

**Key changes:**
- `approve` command **resolves** pending approvals, doesn't trigger gate evaluation
- `reject` command provides feedback for pending approvals
- AI workflows can run fully automated (no `approve` commands if all gates pass)
- Manual workflows pause at PENDING, resume on user command

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Add `PENDING` to `ApprovalDecision` | Explicit state for "awaiting external input" |
| Gates run after content creation | Enables auto-continue for AI approvers |
| `approve` resolves PENDING, doesn't trigger gate | User command IS the resolution, not a gate trigger |
| `reject` resolves PENDING with feedback | Consistent with approve semantics |
| Manual approver claims `fs_ability="local-write"` | Human has full filesystem access |
| Track pending state in `WorkflowState` | Engine knows when to pause vs. auto-continue |

---

## Implementation Steps

### Phase 1: Model Changes

#### Step 1: Add PENDING to ApprovalDecision [TDD]

**File:** `aiwf/domain/models/approval_result.py`

**Test first** (`tests/unit/domain/models/test_approval_result.py`):
```python
def test_pending_decision_exists():
    """PENDING is a valid ApprovalDecision."""
    assert ApprovalDecision.PENDING == "pending"

def test_pending_result_no_feedback_required():
    """PENDING decisions don't require feedback (unlike REJECTED)."""
    result = ApprovalResult(decision=ApprovalDecision.PENDING)
    assert result.decision == ApprovalDecision.PENDING
    assert result.feedback is None

def test_pending_result_with_optional_feedback():
    """PENDING can optionally include feedback."""
    result = ApprovalResult(
        decision=ApprovalDecision.PENDING,
        feedback="Awaiting user review"
    )
    assert result.feedback == "Awaiting user review"

def test_approval_decision_has_three_values():
    """ApprovalDecision has exactly three values."""
    assert set(ApprovalDecision) == {
        ApprovalDecision.APPROVED,
        ApprovalDecision.REJECTED,
        ApprovalDecision.PENDING,
    }
```

**Implementation:**
```python
class ApprovalDecision(str, Enum):
    """Approval decision with three states.

    APPROVED: Content passes, workflow advances
    REJECTED: Content fails, needs correction
    PENDING: Awaiting external input (manual approval)
    """
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
```

**Update validator** - no change needed (only validates REJECTED requires feedback).

**Update docstring** - change "Binary approval decision" to "Approval decision".

---

#### Step 2: Add pending_approval to WorkflowState [TDD]

**File:** `aiwf/domain/models/workflow_state.py`

**Test first** (`tests/unit/domain/models/test_workflow_state.py`):
```python
def test_pending_approval_defaults_false():
    """pending_approval defaults to False."""
    state = WorkflowState(session_id="test", profile_name="test")
    assert state.pending_approval is False

def test_pending_approval_serializes():
    """pending_approval included in JSON serialization."""
    state = WorkflowState(session_id="test", profile_name="test", pending_approval=True)
    data = state.model_dump()
    assert data["pending_approval"] is True

def test_pending_approval_survives_round_trip():
    """pending_approval preserved through save/load cycle."""
    state = WorkflowState(session_id="test", profile_name="test", pending_approval=True)
    json_str = state.model_dump_json()
    loaded = WorkflowState.model_validate_json(json_str)
    assert loaded.pending_approval is True
```

**Implementation:**
```python
class WorkflowState(BaseModel):
    # ... existing fields ...

    # Approval gate state
    pending_approval: bool = Field(
        default=False,
        description="True when workflow is paused waiting for manual approval decision."
    )
```

---

#### Step 3: Update ManualApprovalProvider [TDD]

**File:** `aiwf/domain/providers/approval_provider.py`

**Test first** (`tests/unit/domain/providers/test_manual_approver.py`):
```python
def test_evaluate_returns_pending():
    """ManualApprovalProvider.evaluate() returns PENDING result."""
    provider = ManualApprovalProvider()
    result = provider.evaluate(
        phase=WorkflowPhase.PLAN,
        stage=WorkflowStage.PROMPT,
        files={},
        context={},
    )
    assert isinstance(result, ApprovalResult)
    assert result.decision == ApprovalDecision.PENDING
    assert result.feedback is not None  # Should have message

def test_metadata_fs_ability_local_write():
    """Manual approver claims local-write (human has full access)."""
    metadata = ManualApprovalProvider.get_metadata()
    assert metadata["fs_ability"] == "local-write"

def test_metadata_name():
    """Manual approver metadata has correct name."""
    metadata = ManualApprovalProvider.get_metadata()
    assert metadata["name"] == "manual"
```

**Implementation:**
```python
class ManualApprovalProvider(ApprovalProvider):
    """Manual approval provider. Returns PENDING for user decision.

    When evaluate() is called, returns PENDING to signal the workflow
    should pause and wait for user input. The user then issues
    'approve' or 'reject' to resolve the pending state.
    """

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Return PENDING to signal pause for user input."""
        return ApprovalResult(
            decision=ApprovalDecision.PENDING,
            feedback="Awaiting manual approval. Review content and run 'approve' or 'reject'.",
        )

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "manual",
            "description": "Pause for user approval",
            "fs_ability": "local-write",  # Human has full access
        }
```

---

#### Step 4: Update ApprovalProvider return type

**File:** `aiwf/domain/providers/approval_provider.py`

**Change signature** from `ApprovalResult | None` to `ApprovalResult`:
```python
@abstractmethod
def evaluate(
    self,
    *,
    phase: WorkflowPhase,
    stage: WorkflowStage,
    files: dict[str, str | None],
    context: dict[str, Any],
) -> ApprovalResult:  # Remove | None
    """Evaluate content and return approval decision.

    Returns:
        ApprovalResult with decision:
        - APPROVED: Content passes, workflow advances automatically
        - REJECTED: Content fails, needs correction
        - PENDING: Awaiting external input (workflow pauses)
    """
    ...
```

---

#### Step 5: Remove is_manual_pause helper

**File:** `aiwf/domain/models/approval_result.py`

**Delete** these (no longer needed):
```python
# DELETE:
ApprovalOutcome = ApprovalResult | None

def is_manual_pause(outcome: ApprovalOutcome) -> bool:
    ...
```

**Add migration guard** for external code still returning None:
```python
def validate_approval_result(result: Any) -> ApprovalResult:
    """Validate approval result, catching legacy None returns.

    Raises:
        TypeError: If result is None (legacy provider not updated)
    """
    if result is None:
        raise TypeError(
            "ApprovalProvider.evaluate() returned None. "
            "This is no longer supported. Return ApprovalResult(decision=PENDING) instead."
        )
    return result
```

---

### Phase 2: Engine Changes

#### Step 6: Create _run_gate_after_action method [TDD]

**File:** `aiwf/application/workflow_orchestrator.py`

This new method runs the approval gate and handles all three results.

**Test first** (`tests/unit/application/test_workflow_orchestrator.py`):
```python
class TestGateAfterAction:
    """Tests for automatic gate execution after content creation."""

    def test_approved_result_auto_continues(self):
        """APPROVED result triggers automatic transition to next stage."""
        orchestrator = create_orchestrator_with_approver(
            MockApprover(returns=ApprovalDecision.APPROVED)
        )
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        # Simulate prompt was just created

        orchestrator._run_gate_after_action(state, session_dir)

        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE  # Auto-advanced
        assert state.pending_approval is False

    def test_pending_result_sets_flag_and_pauses(self):
        """PENDING result sets pending_approval and does NOT transition."""
        orchestrator = create_orchestrator_with_approver(
            MockApprover(returns=ApprovalDecision.PENDING)
        )
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)

        orchestrator._run_gate_after_action(state, session_dir)

        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT  # NOT advanced
        assert state.pending_approval is True

    def test_rejected_result_triggers_retry_logic(self):
        """REJECTED result triggers existing retry/rejection handling."""
        orchestrator = create_orchestrator_with_approver(
            MockApprover(returns=ApprovalDecision.REJECTED, feedback="Bad content")
        )
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)

        orchestrator._run_gate_after_action(state, session_dir)

        assert state.approval_feedback == "Bad content"
        # Retry logic exercised (existing behavior)

    def test_gate_error_is_recoverable(self):
        """Gate errors don't crash workflow - state saved for retry."""
        orchestrator = create_orchestrator_with_approver(
            MockApprover(raises=ProviderError("Network timeout"))
        )
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)

        orchestrator._run_gate_after_action(state, session_dir)

        assert "Network timeout" in state.last_error
        assert state.pending_approval is False  # Not pending, errored
```

**Implementation:**
```python
def _run_gate_after_action(
    self,
    state: WorkflowState,
    session_dir: Path,
) -> None:
    """Run approval gate after content creation and handle result.

    Called automatically after CREATE_PROMPT and CALL_AI actions.
    Handles all three decision types:
    - APPROVED: Auto-continue to next stage
    - REJECTED: Trigger retry/rejection handling
    - PENDING: Set flag and pause workflow

    Args:
        state: Current workflow state (modified in place)
        session_dir: Session directory path
    """
    if state.stage is None:
        return  # No gate for stageless states

    try:
        result = self._run_approval_gate(state, session_dir)
        result = validate_approval_result(result)  # Catch legacy None
    except (ProviderError, TimeoutError, TypeError) as e:
        state.last_error = f"Approval gate error: {e}"
        self._add_message(state, f"Approval failed: {e}. Run 'approve' to retry.")
        self.session_store.save(state)
        return

    if result.decision == ApprovalDecision.PENDING:
        # Manual approval needed - pause workflow
        state.pending_approval = True
        if result.feedback:
            self._add_message(state, result.feedback)
        self.session_store.save(state)
        return

    if result.decision == ApprovalDecision.REJECTED:
        # Existing rejection handling (retry, suggested_content, etc.)
        rejection_result = self._handle_approval_rejection(state, session_dir, result)
        if rejection_result is not None:
            # Workflow paused for user intervention
            return
        # Retry succeeded - fall through to auto-continue

    # APPROVED (or retry succeeded) - auto-continue
    self._clear_approval_state(state)
    self._handle_pre_transition_approval(state, session_dir)
    self._auto_continue(state, session_dir)
```

---

#### Step 7: Create _auto_continue method [TDD]

**File:** `aiwf/application/workflow_orchestrator.py`

This method advances to the next stage after approval.

**Test first:**
```python
def test_auto_continue_advances_stage():
    """Auto-continue transitions from PROMPT to RESPONSE."""
    state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
    state.pending_approval = False

    orchestrator._auto_continue(state, session_dir)

    assert state.stage == WorkflowStage.RESPONSE

def test_auto_continue_executes_next_action():
    """Auto-continue executes the action for the new stage."""
    state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)

    with patch.object(orchestrator, '_execute_action') as mock_action:
        orchestrator._auto_continue(state, session_dir)
        mock_action.assert_called_once()

def test_auto_continue_chains_through_skip_approvers():
    """Multiple skip approvers chain without user intervention."""
    # Configure all approvers as 'skip'
    orchestrator = create_orchestrator_with_config({
        "plan.prompt": "skip",
        "plan.response": "skip",
    })
    state = create_state_at(WorkflowPhase.INIT, WorkflowStage.PROMPT)

    # Single init should chain through to GENERATE (if all gates pass)
    result = orchestrator.initialize_run(state.session_id)

    # Workflow auto-advanced through PLAN[PROMPT] and PLAN[RESPONSE]
    assert result.phase == WorkflowPhase.GENERATE
```

**Implementation:**
```python
def _auto_continue(
    self,
    state: WorkflowState,
    session_dir: Path,
) -> None:
    """Automatically continue to next stage after approval.

    Performs the state transition and executes the next action.
    If the next action also passes approval, continues recursively
    (enabling fully automated workflows with skip/AI approvers).

    Args:
        state: Current workflow state
        session_dir: Session directory path
    """
    # Get transition for approve command (same as manual approve)
    transition = TransitionTable.get_transition(state.phase, state.stage, "approve")
    if transition is None:
        return  # No valid transition (shouldn't happen)

    # Update state BEFORE action (ADR-0012)
    state.phase = transition.phase
    state.stage = transition.stage

    # Execute the action for new state
    self._execute_action(state, transition.action, state.session_id)

    # Save state
    self.session_store.save(state)
```

---

#### Step 8: Integrate gate into _execute_action [TDD]

**File:** `aiwf/application/workflow_orchestrator.py`

Call `_run_gate_after_action` after content-creating actions.

**Test first:**
```python
def test_create_prompt_triggers_gate():
    """CREATE_PROMPT action triggers approval gate."""
    orchestrator = create_orchestrator_with_approver(
        MockApprover(returns=ApprovalDecision.PENDING)
    )
    state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)

    orchestrator._execute_action(state, Action.CREATE_PROMPT, state.session_id)

    # Gate was called, PENDING was set
    assert state.pending_approval is True

def test_call_ai_triggers_gate():
    """CALL_AI action triggers approval gate."""
    orchestrator = create_orchestrator_with_approver(
        MockApprover(returns=ApprovalDecision.APPROVED)
    )
    state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)

    orchestrator._execute_action(state, Action.CALL_AI, state.session_id)

    # Gate was called, auto-continued (APPROVED)
    # Verify by checking gate was invoked
```

**Implementation changes to `_execute_action()`:**
```python
def _execute_action(
    self,
    state: WorkflowState,
    action: Action,
    session_id: str,
) -> None:
    """Execute an action after transition.

    After content-creating actions (CREATE_PROMPT, CALL_AI),
    automatically runs the approval gate.
    """
    session_dir = self.sessions_root / session_id

    if action == Action.CREATE_PROMPT:
        self._action_create_prompt(state, session_dir)
        # NEW: Run gate after creating prompt
        self._run_gate_after_action(state, session_dir)

    elif action == Action.CALL_AI:
        self._action_call_ai(state, session_dir)
        # NEW: Run gate after AI response
        self._run_gate_after_action(state, session_dir)

    elif action == Action.CHECK_VERDICT:
        self._action_check_verdict(state, session_dir)

    elif action == Action.FINALIZE:
        self._action_finalize(state, session_dir)

    elif action == Action.HALT:
        pass

    elif action == Action.RETRY:
        self._action_retry(state, session_dir)
```

---

#### Step 9: Update approve command to resolve pending [TDD]

**File:** `aiwf/application/workflow_orchestrator.py`

**Test first:**
```python
class TestApproveCommand:
    """Tests for approve command with new semantics."""

    def test_approve_resolves_pending(self):
        """approve command resolves pending_approval and continues."""
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        state.pending_approval = True
        save_state(state)

        result = orchestrator.approve(state.session_id)

        assert result.pending_approval is False
        assert result.stage == WorkflowStage.RESPONSE  # Transitioned

    def test_approve_without_pending_is_error(self):
        """approve command without pending_approval raises error."""
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        state.pending_approval = False
        save_state(state)

        with pytest.raises(InvalidCommand) as exc:
            orchestrator.approve(state.session_id)

        assert "No pending approval" in str(exc.value)

    def test_approve_with_error_retries_gate(self):
        """approve after gate error retries the gate."""
        state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        state.pending_approval = False
        state.last_error = "Previous gate error"
        save_state(state)

        # This time gate succeeds
        orchestrator = create_orchestrator_with_approver(
            MockApprover(returns=ApprovalDecision.APPROVED)
        )

        result = orchestrator.approve(state.session_id)

        assert result.last_error is None  # Cleared
        assert result.stage == WorkflowStage.RESPONSE  # Transitioned
```

**Implementation:**
```python
def approve(
    self,
    session_id: str,
    hash_prompts: bool = False,  # Legacy, ignored
    fs_ability: str | None = None,  # Legacy, ignored
) -> WorkflowState:
    """Resolve a pending approval and continue workflow.

    Only valid when:
    - pending_approval is True (resolves the pending state)
    - last_error is set (retries failed gate)

    Args:
        session_id: The session to approve

    Returns:
        Updated workflow state

    Raises:
        InvalidCommand: If no pending approval to resolve
    """
    state = self.session_store.load(session_id)
    state.messages = []
    session_dir = self.sessions_root / session_id

    # Check if there's something to resolve
    if not state.pending_approval and not state.last_error:
        raise InvalidCommand(
            "approve",
            state.phase,
            state.stage,
            f"No pending approval to resolve. "
            f"Current state: {state.phase.value}[{state.stage.value if state.stage else 'none'}]. "
            f"Gates run automatically after content creation. "
            f"Use 'status' to see current workflow state."
        )

    # Clear error state if retrying after error
    if state.last_error:
        state.last_error = None
        # Re-run the gate
        self._run_gate_after_action(state, session_dir)
        return state

    # Resolve pending approval
    state.pending_approval = False
    self._clear_approval_state(state)
    self._handle_pre_transition_approval(state, session_dir)
    self._auto_continue(state, session_dir)

    return state
```

---

#### Step 10: Update reject command for pending state [TDD]

**File:** `aiwf/application/workflow_orchestrator.py`

**Test first:**
```python
def test_reject_resolves_pending_with_feedback():
    """reject command resolves pending and stores feedback."""
    state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
    state.pending_approval = True
    save_state(state)

    result = orchestrator.reject(state.session_id, feedback="Plan is incomplete")

    assert result.pending_approval is False
    assert result.approval_feedback == "Plan is incomplete"
    assert result.phase == WorkflowPhase.PLAN  # No transition
    assert result.stage == WorkflowStage.RESPONSE

def test_reject_without_pending_is_error():
    """reject command without pending_approval raises error."""
    state = create_state_at(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
    state.pending_approval = False
    save_state(state)

    with pytest.raises(InvalidCommand):
        orchestrator.reject(state.session_id, feedback="test")
```

**Implementation:**
```python
def reject(self, session_id: str, feedback: str) -> WorkflowState:
    """Reject pending approval with feedback.

    Only valid when pending_approval is True.
    Stores feedback and keeps workflow paused for user to address issues.

    Args:
        session_id: The session to reject
        feedback: Explanation of why content was rejected

    Returns:
        Updated workflow state

    Raises:
        InvalidCommand: If no pending approval to reject
    """
    state = self.session_store.load(session_id)
    state.messages = []

    if not state.pending_approval:
        raise InvalidCommand(
            "reject",
            state.phase,
            state.stage,
            f"No pending approval to reject. "
            f"Current state: {state.phase.value}[{state.stage.value if state.stage else 'none'}]. "
            f"The 'reject' command is only valid when awaiting manual approval."
        )

    state.pending_approval = False
    state.approval_feedback = feedback
    self._add_message(state, f"Rejected: {feedback}")

    self.session_store.save(state)
    return state
```

---

#### Step 11: Remove isinstance checks

**File:** `aiwf/application/workflow_orchestrator.py`

**Delete** all `isinstance(approver, ManualApprovalProvider)` checks.

The old code in `_execute_command`:
```python
# DELETE THIS BLOCK:
approver = self._get_approver(state.phase, state.stage) if state.stage else None
is_manual = isinstance(approver, ManualApprovalProvider)

if is_manual:
    self._clear_approval_state(state)
    self._handle_pre_transition_approval(state, session_dir)
else:
    # ... gate logic
```

This is no longer needed - gates run automatically in `_execute_action`.

---

#### Step 12: Update _run_approval_gate return type

**File:** `aiwf/application/workflow_orchestrator.py`

Change signature and remove None handling:
```python
def _run_approval_gate(
    self,
    state: WorkflowState,
    session_dir: Path,
) -> ApprovalResult:  # Remove | None
    """Run approval gate for current phase/stage.

    Returns:
        ApprovalResult (never None - PENDING replaces None for manual)
    """
    # ... existing implementation, remove None return paths
```

---

### Phase 3: Documentation & Tests

#### Step 13: Update ADR-0015

**File:** `docs/adr/0015-approval-provider-implementation.md`

Update to reflect new architecture. Key changes:
- Gates run after content creation, not on approve command
- PENDING is explicit third state
- approve/reject resolve pending states
- Fully automated workflows possible

#### Step 14: Update Specification

**File:** `docs/plans/adr0015-approval-providers.md`

**Replace "Manual Approver Behavior" section:**

```markdown
### Manual Approver Behavior

**Contract:** Gates run automatically; PENDING pauses workflow; user command resolves.

Approval gates run immediately after content creation (CREATE_PROMPT, CALL_AI actions).
The engine calls `evaluate()` uniformly for all providers:

| Result | Engine Behavior |
|--------|-----------------|
| APPROVED | Auto-continue to next stage |
| REJECTED | Handle rejection (retry, suggested_content, halt) |
| PENDING | Set `pending_approval=True`, save state, exit |

For manual approvers:
1. Gate runs after content is created
2. `ManualApprovalProvider.evaluate()` returns `PENDING`
3. Engine sets `pending_approval=True` and exits cleanly
4. User reviews content
5. User issues `approve` → resolves pending, workflow continues
6. User issues `reject --feedback "..."` → stores feedback, workflow paused

This design:
- Eliminates `isinstance` checks
- Treats all providers uniformly
- Enables fully automated workflows (all skip/AI approvers)
```

#### Step 15: Update existing tests

**Files to update:**
- `tests/unit/domain/models/test_approval_result.py` - Update for three-state enum
- `tests/unit/application/test_behavioral_contracts.py` - Update manual approver contract tests
- `tests/integration/test_workflow_manual_provider.py` - Update for new flow

**Key test changes:**
```python
# Old: Test that approve command triggers gate
# New: Test that approve command resolves pending

# Old: Test that manual approver returns None
# New: Test that manual approver returns PENDING

# Old: Test binary decision enum
# New: Test three-state decision enum
```

---

## Files Changed

| File | Change |
|------|--------|
| `aiwf/domain/models/approval_result.py` | Add PENDING; remove `is_manual_pause()`; add `validate_approval_result()` |
| `aiwf/domain/models/workflow_state.py` | Add `pending_approval: bool` |
| `aiwf/domain/providers/approval_provider.py` | Update `ManualApprovalProvider`; fix return types |
| `aiwf/application/workflow_orchestrator.py` | Add `_run_gate_after_action()`, `_auto_continue()`; update `approve()`, `reject()`, `_execute_action()`; remove isinstance checks |
| `docs/adr/0015-approval-provider-implementation.md` | Update for new architecture |
| `docs/plans/adr0015-approval-providers.md` | Update specification |
| `tests/unit/domain/models/test_approval_result.py` | Tests for PENDING, three-state enum |
| `tests/unit/domain/models/test_workflow_state.py` | Tests for `pending_approval` |
| `tests/unit/domain/providers/test_manual_approver.py` | Tests for PENDING behavior |
| `tests/unit/application/test_workflow_orchestrator.py` | Tests for auto-continue, gate timing |
| `tests/unit/application/test_behavioral_contracts.py` | Update contract tests |
| `tests/integration/test_workflow_manual_provider.py` | Update integration tests |

---

## Test Summary

| Step | TDD | New Tests |
|------|-----|-----------|
| 1. PENDING decision | Yes | 4 |
| 2. pending_approval field | Yes | 3 |
| 3. ManualApprovalProvider | Yes | 3 |
| 4-5. Type changes | No | 0 |
| 6. _run_gate_after_action | Yes | 4 |
| 7. _auto_continue | Yes | 3 |
| 8. Gate in _execute_action | Yes | 2 |
| 9. approve command | Yes | 3 |
| 10. reject command | Yes | 2 |
| 11-12. Refactoring | No | 0 |
| 13-15. Docs & test updates | No | ~10 updated |
| **Total** | | **24 new tests** |

---

## Acceptance Criteria

- [ ] `ApprovalDecision.PENDING` exists and works
- [ ] `ApprovalDecision` has exactly three values
- [ ] `ManualApprovalProvider.evaluate()` returns `ApprovalResult(decision=PENDING)`
- [ ] `ManualApprovalProvider.get_metadata()` returns `fs_ability="local-write"`
- [ ] No `isinstance(approver, ManualApprovalProvider)` in codebase
- [ ] Gates run automatically after CREATE_PROMPT and CALL_AI actions
- [ ] APPROVED result triggers auto-continue to next stage
- [ ] PENDING result sets `pending_approval=True` and pauses workflow
- [ ] REJECTED result triggers existing retry/rejection handling
- [ ] `approve` command resolves pending approval
- [ ] `approve` without pending raises InvalidCommand
- [ ] `reject` command resolves pending with feedback
- [ ] `reject` without pending raises InvalidCommand
- [ ] Fully automated workflow works (all skip approvers, no manual commands)
- [ ] All existing tests pass (with updates)
- [ ] 24 new tests added and passing
- [ ] ADR and specification documents updated

---

## Migration Notes

This is a **significant architectural change**:

**Before:**
- Gates triggered by user `approve` command
- Manual approvers detected by `isinstance` and bypassed
- All workflows require explicit `approve` commands

**After:**
- Gates run automatically after content creation
- All providers return `ApprovalResult` (APPROVED/REJECTED/PENDING)
- APPROVED auto-continues, PENDING pauses
- `approve` command resolves pending states only

**User-facing changes:**
- Workflows with all skip/AI approvers run to completion automatically
- Manual workflows behave the same (pause, review, approve)
- `approve` without pending approval now raises an error

**Breaking changes:**
- Custom `ApprovalProvider` implementations returning `None` will raise `TypeError`
- Code checking `isinstance(ManualApprovalProvider)` needs update
- Code assuming `approve` triggers gate needs update

---

## Sequence Diagrams

### Fully Automated Workflow (Skip/AI Approvers)

```
User                    Engine                  Approver
  |                        |                        |
  |-- init --------------->|                        |
  |                        |-- CREATE_PROMPT ------>|
  |                        |<-- APPROVED -----------|
  |                        |-- (auto-continue) ---->|
  |                        |-- CALL_AI ------------>|
  |                        |<-- APPROVED -----------|
  |                        |-- (auto-continue) ---->|
  |                        |        ...             |
  |<-- COMPLETE -----------|                        |
```

### Manual Workflow

```
User                    Engine                  ManualApprover
  |                        |                        |
  |-- init --------------->|                        |
  |                        |-- CREATE_PROMPT ------>|
  |                        |<-- PENDING ------------|
  |                        |-- (save, exit) ------->|
  |<-- "awaiting approval" |                        |
  |                        |                        |
  |   (user reviews)       |                        |
  |                        |                        |
  |-- approve ------------>|                        |
  |                        |-- (resolve pending) -->|
  |                        |-- (auto-continue) ---->|
  |                        |-- CALL_AI ------------>|
  |                        |<-- PENDING ------------|
  |<-- "awaiting approval" |                        |
  |                        |                        |
  |-- approve ------------>|                        |
  |                        |        ...             |
```
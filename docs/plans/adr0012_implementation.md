# ADR-0012 Implementation Plan

## Design Pattern: Strategy + Explicit State Machine (Option D)

**State Machine** - Handles WHAT transitions are valid
**Strategy** - Handles HOW work gets done (AI providers, approval providers)
**Factory** - Creates provider instances from configuration

---

## Progress Tracking

> **For AI agents continuing this work:** Check this section first. Update after each commit.

| Phase | Status | Commit | Notes |
|-------|--------|--------|-------|
| 0. Cleanup | DONE | 1d4b23b | Deleted 42 test files, 441 remain |
| 1. Models | DONE | e0ca08d | New enums, ApprovalResult, stage field added |
| 2. State Machine | DONE | - | TransitionTable, 68 tests, Action enum |
| 3. Approval Providers | DONE | - | ApprovalProvider ABC, Skip/Manual/AI providers, 35 tests |
| 4. Provider Factory | NOT STARTED | - | |
| 5. Orchestrator | NOT STARTED | - | |
| 6. CLI | NOT STARTED | - | |
| 7. Final Cleanup | NOT STARTED | - | |

**Current Phase:** 4 (Provider Factory)
**Next Action:** Implement ApprovalProviderFactory with registration

---

## Test Approach

### Philosophy
- **TDD where spec is clear** (Phases 1-3, especially Phase 2)
- **Test-after for integration** (Phase 5 integration tests)
- **Old tests deleted, not migrated** (fundamental model change)

### Test Organization
```
tests/
  unit/
    domain/
      models/
        test_workflow_state.py      # Phase 1: enums, state model
        test_approval_result.py     # Phase 1: decision/result models
      providers/
        test_skip_approver.py       # Phase 3
        test_manual_approver.py     # Phase 3
        test_ai_approver.py         # Phase 3
    application/
      test_transitions.py           # Phase 2: state machine
      test_orchestrator.py          # Phase 5: unit tests (mocked)
  integration/
    test_manual_workflow.py         # Full manual flow
    test_automated_workflow.py      # Full auto flow
    test_mixed_workflow.py          # AI + manual approval
```

### TDD Patterns by Phase

**Phase 1 (Models):** Validation-driven
```python
def test_approval_result_requires_feedback_on_rejection():
    with pytest.raises(ValidationError):
        ApprovalResult(decision=ApprovalDecision.REJECTED, feedback=None)
```

**Phase 2 (State Machine):** Table-driven
```python
@pytest.mark.parametrize("current,command,expected", [
    ((Phase.INIT, None), "step", (Phase.PLAN, Stage.PROMPT)),
    ((Phase.PLAN, Stage.PROMPT), "approve", (Phase.PLAN, Stage.RESPONSE)),
    # ... entire transition table
])
def test_transitions(current, command, expected):
    result = TransitionTable.get_transition(*current, command)
    assert (result.phase, result.stage) == expected
```

**Phase 3 (Providers):** Interface contract tests
```python
def test_skip_approver_always_approves():
    result = SkipApprovalProvider().evaluate(...)
    assert result.decision == ApprovalDecision.APPROVED

def test_manual_approver_requires_user_input():
    assert ManualApprovalProvider().requires_user_input is True
```

**Phase 5 (Orchestrator):** Unit + integration split
- Unit: Mock providers, test orchestration logic
- Integration: Real file I/O, mock only AI calls

### What NOT to TDD
- File path helpers
- CLI output formatting
- Error message strings

---

## Phase 1: Domain Models

**Goal:** New enums and models for phase+stage representation.

**Files:**
- `aiwf/domain/models/workflow_state.py` - Update WorkflowPhase, add WorkflowStage
- `aiwf/domain/models/approval_result.py` - New file

**Changes:**

```python
# workflow_state.py
class WorkflowPhase(str, Enum):
    INIT = "init"
    PLAN = "plan"
    GENERATE = "generate"
    REVIEW = "review"
    REVISE = "revise"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"

class WorkflowStage(str, Enum):
    PROMPT = "prompt"      # Prompt ready, awaiting AI/user response
    RESPONSE = "response"  # Response received, awaiting approval

class WorkflowState(BaseModel):
    phase: WorkflowPhase
    stage: WorkflowStage | None  # None for terminal phases
    pending_approval: bool = False
    retry_count: int = 0
    # ... existing fields
```

```python
# approval_result.py
class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"

class ApprovalResult(BaseModel):
    decision: ApprovalDecision
    feedback: str | None = None
```

**Tests:** Unit tests for model validation, serialization.

---

## Phase 2: State Machine

**Goal:** Explicit transition table with validation.

**Files:**
- `aiwf/application/transitions.py` - New file

**Design:**

```python
class TransitionTable:
    """Declarative state transitions."""

    # (current_phase, current_stage, command) -> (next_phase, next_stage, action)
    TRANSITIONS: dict[tuple, tuple] = {
        # From INIT
        (Phase.INIT, None, "step"): (Phase.PLAN, Stage.PROMPT, Action.CREATE_PROMPT),

        # From PLAN[PROMPT]
        (Phase.PLAN, Stage.PROMPT, "approve"): (Phase.PLAN, Stage.RESPONSE, Action.CALL_AI),

        # From PLAN[RESPONSE]
        (Phase.PLAN, Stage.RESPONSE, "approve"): (Phase.GENERATE, Stage.PROMPT, Action.CREATE_PROMPT),
        (Phase.PLAN, Stage.RESPONSE, "reject"): (Phase.PLAN, Stage.RESPONSE, Action.HALT),
        (Phase.PLAN, Stage.RESPONSE, "retry"): (Phase.PLAN, Stage.PROMPT, Action.RETRY),

        # ... similar for GENERATE, REVIEW, REVISE

        # Terminal transitions
        (Phase.REVIEW, Stage.RESPONSE, "approve"): (Phase.COMPLETE, None, Action.FINALIZE),
        # Or if revision needed:
        (Phase.REVIEW, Stage.RESPONSE, "reject"): (Phase.REVISE, Stage.PROMPT, Action.CREATE_PROMPT),
    }

    @classmethod
    def get_transition(cls, phase, stage, command) -> tuple | None:
        return cls.TRANSITIONS.get((phase, stage, command))

    @classmethod
    def valid_commands(cls, phase, stage) -> list[str]:
        """Return commands valid from current state."""
        return [cmd for (p, s, cmd) in cls.TRANSITIONS if p == phase and s == stage]
```

**Tests:**
- All valid transitions return correct next state
- Invalid transitions return None
- `valid_commands()` returns correct set for each state

---

## Phase 3: Approval Provider Abstraction

**Goal:** Strategy pattern for approval decisions.

**Files:**
- `aiwf/domain/providers/approval_provider.py` - New ABC
- `aiwf/domain/providers/skip_approver.py` - Auto-approve
- `aiwf/domain/providers/manual_approver.py` - Pause for user
- `aiwf/domain/providers/ai_approver.py` - Delegate to AI

**Design:**

```python
# approval_provider.py
class ApprovalProvider(ABC):
    @abstractmethod
    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Evaluate content and return decision."""
        ...

    @property
    @abstractmethod
    def requires_user_input(self) -> bool:
        """True if this provider pauses for user interaction."""
        ...


# skip_approver.py
class SkipApprovalProvider(ApprovalProvider):
    def evaluate(self, **kwargs) -> ApprovalResult:
        return ApprovalResult(decision=ApprovalDecision.APPROVED)

    @property
    def requires_user_input(self) -> bool:
        return False


# manual_approver.py
class ManualApprovalProvider(ApprovalProvider):
    def evaluate(self, **kwargs) -> ApprovalResult:
        # This shouldn't be called - manual approval comes from CLI
        raise RuntimeError("ManualApprovalProvider.evaluate() should not be called")

    @property
    def requires_user_input(self) -> bool:
        return True


# ai_approver.py
class AIApprovalProvider(ApprovalProvider):
    def __init__(self, ai_provider: AIProvider, approval_prompt_template: str):
        self._ai = ai_provider
        self._template = approval_prompt_template

    def evaluate(self, *, files, context, **kwargs) -> ApprovalResult:
        prompt = self._build_prompt(files, context)
        response = self._ai.generate(prompt)
        return self._parse_response(response)

    @property
    def requires_user_input(self) -> bool:
        return False
```

**Tests:** Unit tests for each provider implementation.

---

## Phase 4: Provider Registry

**Goal:** Factory for creating providers from configuration.

**Files:**
- `aiwf/domain/providers/approval_factory.py` - New factory
- Update `aiwf/application/config_loader.py` - New config schema

**Config Schema:**

```yaml
providers:
  plan:
    ai: claude
    approver: manual
    max_retries: 3
  generate:
    ai: claude
    approver: skip
    max_retries: 3
  review:
    ai: gpt
    approver: manual
    max_retries: 3
  revise:
    ai: claude
    approver: skip
    max_retries: 3
```

**Factory:**

```python
class ApprovalProviderFactory:
    _providers: dict[str, type[ApprovalProvider]] = {
        "skip": SkipApprovalProvider,
        "manual": ManualApprovalProvider,
    }

    @classmethod
    def register(cls, key: str, provider_class: type[ApprovalProvider]):
        cls._providers[key] = provider_class

    @classmethod
    def create(cls, key: str) -> ApprovalProvider:
        if key in cls._providers:
            return cls._providers[key]()
        # Assume it's an AI provider key
        ai_provider = ProviderFactory.create(key)
        return AIApprovalProvider(ai_provider, APPROVAL_PROMPT_TEMPLATE)
```

**Tests:** Factory creates correct provider types.

---

## Phase 5: Orchestrator Rewrite

**Goal:** New orchestrator using state machine and strategies.

**Files:**
- `aiwf/application/workflow_orchestrator.py` - Major rewrite

**Design:**

```python
class WorkflowOrchestrator:
    def __init__(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        ai_factory: ProviderFactory,
        approval_factory: ApprovalProviderFactory,
        config: WorkflowConfig,
    ):
        self._sessions_root = sessions_root
        self._store = session_store
        self._ai_factory = ai_factory
        self._approval_factory = approval_factory
        self._config = config

    def step(self, session_id: str) -> WorkflowState:
        """Advance workflow to next phase."""
        state = self._store.load(session_id)
        transition = TransitionTable.get_transition(state.phase, state.stage, "step")
        if not transition:
            raise InvalidCommand("step", state.phase, state.stage)

        next_phase, next_stage, action = transition
        state = self._execute_action(state, action, session_id)
        state.phase = next_phase
        state.stage = next_stage

        # Check if approval gate auto-approves
        state = self._check_approval_gate(state, session_id)

        self._store.save(state)
        return state

    def approve(self, session_id: str) -> WorkflowState:
        """Approve pending content."""
        state = self._store.load(session_id)
        transition = TransitionTable.get_transition(state.phase, state.stage, "approve")
        if not transition:
            raise InvalidCommand("approve", state.phase, state.stage)

        next_phase, next_stage, action = transition
        state = self._execute_action(state, action, session_id)
        state.phase = next_phase
        state.stage = next_stage
        state.pending_approval = False

        # Check next approval gate
        state = self._check_approval_gate(state, session_id)

        self._store.save(state)
        return state

    def reject(self, session_id: str, feedback: str) -> WorkflowState:
        """Reject pending content (manual approver only)."""
        ...

    def retry(self, session_id: str, feedback: str) -> WorkflowState:
        """Retry with feedback."""
        ...

    def _check_approval_gate(self, state: WorkflowState, session_id: str) -> WorkflowState:
        """Check approver and auto-approve if skip, or set pending if manual."""
        approver = self._get_approver(state.phase, state.stage)

        if isinstance(approver, SkipApprovalProvider):
            # Auto-approve, continue to next transition
            return self.approve(session_id)

        if approver.requires_user_input:
            state.pending_approval = True
            return state

        # AI approver - evaluate
        result = approver.evaluate(
            phase=state.phase,
            stage=state.stage,
            files=self._get_files(state, session_id),
            context=self._get_context(state),
        )

        if result.decision == ApprovalDecision.APPROVED:
            return self.approve(session_id)
        else:
            # Rejected - auto-retry
            return self._handle_rejection(state, session_id, result.feedback)
```

**Tests:** Integration tests for full workflow scenarios.

---

## Phase 6: CLI Updates

**Goal:** Add reject and retry commands.

**Files:**
- `aiwf/interface/cli/cli.py` - Add commands
- `aiwf/interface/cli/output_models.py` - Add output models

**Commands:**

```python
@cli.command()
@click.argument("session_id")
@click.option("--feedback", "-f", help="Feedback explaining rejection")
def reject(session_id: str, feedback: str | None):
    """Reject pending content."""
    ...

@cli.command()
@click.argument("session_id")
@click.option("--feedback", "-f", required=True, help="Feedback for regeneration")
def retry(session_id: str, feedback: str):
    """Retry generation with feedback."""
    ...
```

**Tests:** CLI integration tests.

---

## Phase 7: Migration & Cleanup

**Goal:** Remove old code, update tests.

**Tasks:**
- Remove old `WorkflowPhase` values (PLANNING, PLANNED, etc.)
- Remove Chain of Responsibility handlers (replaced by state machine)
- Update all tests to use new model
- Update CLAUDE.md documentation

---

## Implementation Order

1. **Phase 1** - Models (foundation, no breaking changes yet)
2. **Phase 2** - State Machine (can test in isolation)
3. **Phase 3** - Approval Providers (can test in isolation)
4. **Phase 4** - Factory (wire up providers)
5. **Phase 5** - Orchestrator (big change, integrates everything)
6. **Phase 6** - CLI (expose new functionality)
7. **Phase 7** - Cleanup (remove old code)

Each phase should be a separate commit with passing tests.

---

## Risk Mitigation

- **Large refactor risk:** Each phase is independently testable
- **Regression risk:** Keep old tests running until Phase 7
- **Config migration:** v2.0 clean break, no migration needed

---

## Success Criteria

1. All state transitions explicit in `TransitionTable`
2. No phase transition logic in orchestrator methods (only action execution)
3. Providers are independently testable strategies
4. `valid_commands(phase, stage)` returns correct options for any state
5. Full workflow runs with: manual/manual, automated/skip, automated/AI configurations
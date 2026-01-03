# Approval Providers Specification

**Status:** COMPLETE
**ADR:** [ADR-0015](../adr/0015-approval-provider-implementation.md)
**Last Updated:** January 2, 2026

---

## Overview

The approval provider system implements automated workflow gates. This includes the `ApprovalProvider` ABC, `AIApprovalProvider` adapter, factory, prompt templates, and orchestrator integration.

**Key components:**
1. `ApprovalProvider` abstract base class
2. `AIApprovalProvider` adapter wrapping `ResponseProvider`
3. `SkipApprovalProvider` and `ManualApprovalProvider` built-ins
4. Standardized approval prompt templates
5. Orchestrator integration with retry logic
6. State fields for approval tracking

---

## Behavioral Contracts

These implementation-level behaviors derive from ADR-0015 design decisions.

### Gate Ordering

**Contract:** Approval gate runs BEFORE artifact hashing.

The approval gate must evaluate and approve content before it becomes immutable. Sequence:
1. Content created (prompt or response)
2. Approval gate evaluates content
3. If approved: hash computed, state updated, transition proceeds
4. If rejected: no hash, content remains editable

**Rationale:** Hash-then-approve would lock unapproved content.

### retry_count Lifecycle

**Contract:** `retry_count` resets to 0 on stage change.

Each stage gets a fresh retry budget. A difficult PROMPT stage shouldn't consume the RESPONSE stage's retry budget.

```
PLAN[PROMPT] retry_count=2 → approve → PLAN[RESPONSE] retry_count=0
```

**Clear conditions:**
- Reset to 0 when stage changes (PROMPT→RESPONSE or phase transition)
- Increment on each rejection within same stage
- Preserved across session save/load within same stage

### Manual Approver Behavior

**Contract:** User's CLI `approve` command IS the approval decision for manual approvers.

The orchestrator detects ManualApprovalProvider and skips the gate evaluation entirely. The user's `approve` command constitutes the approval decision - no separate gate check needed.

```python
# Orchestrator logic (on approve command)
approver = self._get_approver(state.phase, state.stage)
if isinstance(approver, ManualApprovalProvider):
    # User's approve command IS the decision - no gate run
    self._clear_approval_state(state)
    self._handle_pre_transition_approval(state, session_dir)
    # Proceed with stage transition immediately
else:
    # AI/Skip approvers: run the gate
    result = self._run_approval_gate(state, session_dir)
    # ... handle result
```

**Key insight:** For manual approvers, the user reviewing the artifact and issuing `approve` is semantically equivalent to the gate returning APPROVED.

### Response Parsing

**Contract:** Lenient parsing with fallback to rejection.

AI responses vary in format. The parser:
1. Looks for `DECISION: APPROVED` or `DECISION: REJECTED` (case-insensitive)
2. If not found, searches for keywords: "approved" vs "rejected"
3. If ambiguous or unparseable, defaults to REJECTED with feedback "Unable to parse approval response"

```python
# Parsing priority
1. Explicit DECISION line → use that
2. Contains "approved" but not "rejected" → APPROVED
3. Contains "rejected" → REJECTED
4. Neither/both → REJECTED (parse failure)
```

### suggested_content Handling

**Contract:** `suggested_content` is a hint passed to the provider in retry context.

When AI approver rejects with `suggested_content`:
1. Store in `state.suggested_content`
2. On retry, include in provider context: `context["suggested_content"] = state.suggested_content`
3. Provider decides whether/how to use it
4. Approver NEVER writes to files directly

### PROMPT Rejection and Regeneration

**Contract:** PROMPT rejection cannot auto-retry unless profile declares `can_regenerate_prompts`.

Prompts are profile-generated, not AI-generated. Auto-retry (calling AI provider) doesn't apply.

```python
# Orchestrator logic on PROMPT rejection
if stage == WorkflowStage.PROMPT:
    profile_meta = profile.get_metadata()
    if profile_meta.get("can_regenerate_prompts", False):
        # Call profile.regenerate_prompt(phase, feedback, context)
        new_prompt = profile.regenerate_prompt(...)
        # Write and re-evaluate
    else:
        # Cannot auto-retry - stay IN_PROGRESS for user intervention
        state.last_error = f"Prompt rejected: {feedback}. Edit and retry manually."
```

### max_retries Exhaustion

**Contract:** When `retry_count > max_retries`, workflow remains `IN_PROGRESS` (not ERROR).

`IN_PROGRESS` semantics: "waiting on user/LLM response" - which is correct. The workflow is paused for user intervention, not failed.

User can:
- Review rejection feedback in `state.approval_feedback`
- Edit content and retry manually (`aiwf retry`)
- Cancel if appropriate (`aiwf cancel`)

ERROR implies system/technical failure, not approval disagreement.

### Context Builder Pattern

**Contract:** Use base context builder with extension for approval-specific keys.

```python
def _build_base_context(self, state: WorkflowState) -> dict[str, Any]:
    """Base context shared by providers and approvers."""
    ctx = {
        **state.context,
        "session_id": state.session_id,
        "iteration": state.current_iteration,
        "metadata": state.metadata,
    }
    if state.approval_feedback:
        ctx["approval_feedback"] = state.approval_feedback
    if state.suggested_content:
        ctx["suggested_content"] = state.suggested_content
    return ctx

def _build_approval_context(self, state: WorkflowState, session_dir: Path) -> dict[str, Any]:
    """Context for approval providers - extends base with approval-specific keys."""
    ctx = self._build_base_context(state)
    stage_config = self.approval_config.get_stage_config(
        state.phase.value, state.stage.value if state.stage else "prompt"
    )
    ctx.update({
        "allow_rewrite": stage_config.allow_rewrite,
        "session_dir": str(session_dir),
        "plan_file": str(session_dir / "plan.md"),
    })
    return ctx
```

### Files/Context Contract per Gate

AI approvers receive `files` dict and `context` dict. Contents vary by gate:

| Gate | files dict | context keys |
|------|------------|--------------|
| PLAN[PROMPT] | `planning-prompt.md` | `session_dir`, `criteria_file` |
| PLAN[RESPONSE] | `planning-prompt.md`, `planning-response.md` | `session_dir`, `criteria_file` |
| GENERATE[PROMPT] | `generation-prompt.md`, `plan.md` | `session_dir`, `iteration` |
| GENERATE[RESPONSE] | `generation-prompt.md`, code files | `session_dir`, `iteration`, `plan_file` |
| REVIEW[PROMPT] | `review-prompt.md`, code files | `session_dir`, `iteration` |
| REVIEW[RESPONSE] | `review-prompt.md`, `review-response.md` | `session_dir`, `iteration` |
| REVISE[PROMPT] | `revision-prompt.md`, `review-response.md` | `session_dir`, `iteration` |
| REVISE[RESPONSE] | `revision-prompt.md`, code files, `revision-issues.md` | `session_dir`, `iteration` |

---

## ApprovalProvider Interface

**File:** `aiwf/domain/providers/approval_provider.py`

```python
class ApprovalProvider(ABC):
    """Abstract base class for approval providers."""

    @abstractmethod
    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Evaluate content and return approval decision."""
        ...

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata."""
        return {
            "name": "base",
            "description": "Base approval provider",
            "fs_ability": "none",
        }
```

### SkipApprovalProvider

```python
class SkipApprovalProvider(ApprovalProvider):
    """Auto-approve provider. Always returns APPROVED."""

    def evaluate(self, *, phase, stage, files, context) -> ApprovalResult:
        return ApprovalResult(decision="approved")
```

### ManualApprovalProvider

```python
class ManualApprovalProvider(ApprovalProvider):
    """Manual approval provider. User's approve command IS the decision."""

    def evaluate(self, *, phase, stage, files, context) -> ApprovalResult | None:
        return None  # Signals "pause for user" (bypassed by orchestrator)
```

---

## AIApprovalProvider Adapter

**File:** `aiwf/domain/providers/ai_approval_provider.py`

Wraps a `ResponseProvider` to serve as an approval gate:

```python
class AIApprovalProvider(ApprovalProvider):
    """Adapter that wraps ResponseProvider for approval evaluation."""

    def __init__(self, response_provider: ResponseProvider, criteria_file: str | None = None):
        self._provider = response_provider
        self._criteria_file = criteria_file

    def evaluate(self, *, phase, stage, files, context) -> ApprovalResult:
        prompt = self._build_approval_prompt(phase, stage, files, context)
        result = self._provider.generate(prompt, context)

        if result is None or result.response is None:
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Provider returned no response text for approval evaluation",
            )

        return self._parse_response(result.response)
```

### Prompt Templates

All templates require explicit `DECISION: APPROVED` or `DECISION: REJECTED`:

```
**CRITICAL: You MUST respond with exactly the word "APPROVED" or "REJECTED" on the DECISION line.**

## Response Format (REQUIRED)
DECISION: APPROVED
or
DECISION: REJECTED
```

---

## ApprovalProviderFactory

**File:** `aiwf/domain/providers/approval_factory.py`

```python
class ApprovalProviderFactory:
    """Factory for creating approval providers."""

    _registry: ClassVar[dict[str, type[ApprovalProvider]]] = {}

    @classmethod
    def create(cls, key: str, config: dict[str, Any] | None = None) -> ApprovalProvider:
        """Create approval provider by key."""
        if key in cls._registry:
            return cls._registry[key](config)

        # Fallback: wrap ResponseProvider as AIApprovalProvider
        response_provider = ResponseProviderFactory.create(key, config)
        metadata = response_provider.get_metadata()

        # Validate fs_ability
        if metadata.get("fs_ability") == "none":
            raise ValueError(
                f"Provider {key!r} has fs_ability='none' and cannot be used for approval."
            )

        return AIApprovalProvider(response_provider)
```

---

## State Fields

**File:** `aiwf/domain/models/workflow_state.py`

```python
class WorkflowState(BaseModel):
    # Approval tracking (cleared on stage change)
    approval_feedback: str | None = Field(
        default=None,
        description="Feedback from last rejection. Cleared when stage changes."
    )
    suggested_content: str | None = Field(
        default=None,
        description="Suggested content from approver. Cleared when stage changes."
    )
    retry_count: int = Field(
        default=0,
        description="Retry attempts in current stage. Resets on stage change."
    )
```

---

## Configuration

**File:** `aiwf/application/approval_config.py`

```yaml
# Simple format
plan.prompt: skip
plan.response: claude-code
generate.response: manual

# Full format
default_approver: manual
default_max_retries: 0
default_allow_rewrite: false
stages:
  plan.response:
    approver: claude-code
    max_retries: 3
    allow_rewrite: true
```

---

## Test Organization

```
tests/
  unit/
    domain/providers/
      test_approval_provider.py     # Provider unit tests
      test_approval_factory.py      # Factory unit tests
      test_ai_approver.py           # AI approver parsing tests
    application/
      test_approval_config.py       # Config tests
      test_behavioral_contracts.py  # Contract verification tests
  integration/
    test_approval_flow.py           # 12-scenario end-to-end tests
```

### Integration Test Matrix

| # | Test | Scenario |
|---|------|----------|
| 1 | `test_full_workflow_with_skip_approvers` | Complete workflow with skip gates |
| 2 | `test_manual_approver_pauses_at_prompt` | Manual gate at PROMPT |
| 3 | `test_manual_approver_pauses_at_response` | Manual gate at RESPONSE |
| 4 | `test_ai_approver_approves_and_advances` | AI approves, workflow advances |
| 5 | `test_ai_approver_rejects_then_retries_and_succeeds` | Retry succeeds |
| 6 | `test_ai_approver_exhausts_max_retries` | Max retries exhausted |
| 7 | `test_prompt_rejection_pauses_without_regeneration` | PROMPT rejected, no regen |
| 8 | `test_prompt_rejection_with_regeneration_succeeds` | PROMPT rejected, regen works |
| 9 | `test_suggested_content_applied_to_prompt` | suggested_content for PROMPT |
| 10 | `test_suggested_content_stored_for_response` | suggested_content for RESPONSE |
| 11 | `test_retry_count_resets_on_stage_change` | retry_count lifecycle |
| 12 | `test_mixed_approver_configuration` | Mixed skip/manual/AI config |

---

## Related Documents

- [ADR-0015: Approval Provider Implementation](../adr/0015-approval-provider-implementation.md)
- [ADR-0012: Workflow Phases, Stages, and Approval Providers](../adr/0012-workflow-phases-stages-approval-providers.md)
- [ADR-0013: Claude Code Provider](../adr/0013-claude-code-provider.md)
- [ADR-0014: Gemini CLI Provider](../adr/0014-gemini-cli-provider.md)

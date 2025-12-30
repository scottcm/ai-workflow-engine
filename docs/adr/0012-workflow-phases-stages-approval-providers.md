# ADR-0012: Workflow Phases, Stages, and Approval Providers

**Status:** Draft
**Date:** December 30, 2024
**Deciders:** Scott

---

## Context and Problem Statement

The current workflow implementation has several issues:

1. **Conflated responsibilities**: `approve()` both commits approval AND calls AI providers
2. **Confusing phase model**: 10+ discrete phases (PLANNING, PLANNED, GENERATING, GENERATED, etc.) when conceptually there are 4 phases with 2 stages each
3. **No approval provider abstraction**: Approval is either manual or auto-approved by profile flag, with no way to delegate approval decisions to AI
4. **No reject command**: Users can only approve; there's no explicit rejection path
5. **Poor UX**: Requires multiple step/approve commands to progress through workflow

This ADR proposes a redesigned workflow model that cleanly separates phases, stages, AI providers, and approval providers.

---

## Decision Drivers

1. Clear mental model for users and developers
2. Separation of concerns: content creation vs approval decisions
3. Flexible automation: fully manual, fully automated, or mixed workflows
4. Extensibility: custom approval logic without engine changes
5. Good UX: minimal commands for common workflows

---

## Key Insight: Execution Mode Determines Valid Approver Types

**Execution mode and approver type are not orthogonal.** A workflow is only truly automated if it can run without human intervention. Therefore:

| Execution Mode | Valid Approvers | Invalid Approvers |
|----------------|-----------------|-------------------|
| Interactive | `manual`, `skip`, AI provider | - |
| Automated | `skip`, AI provider | `manual` |

**Rationale**: "Automated + manual approval" is a contradiction. If a human must approve content, the workflow is interactive by definition, regardless of whether AI generates the content.

---

## Decision Outcome

### Phase and Stage Model

Replace discrete phases with a phase + stage model:

| Phase | Purpose |
|-------|---------|
| INIT | Session initialized, ready to start |
| PLAN | Create development plan |
| GENERATE | Generate code artifacts |
| REVIEW | Review generated code |
| REVISE | Revise code based on review feedback |
| COMPLETE | Workflow finished successfully |
| ERROR | Workflow stopped due to error |
| CANCELLED | Workflow cancelled by user |

Each phase (except INIT, COMPLETE, ERROR, CANCELLED) has two stages:

| Stage | Purpose |
|-------|---------|
| ING | Input preparation - prompt created, awaiting approval before AI processing |
| ED | Output review - AI response received, awaiting approval before advancement |

### State Representation

```python
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
    ING = "ing"  # Input preparation
    ED = "ed"    # Output review

class WorkflowState(BaseModel):
    phase: WorkflowPhase
    stage: WorkflowStage | None  # None for INIT, COMPLETE, ERROR, CANCELLED
    # ... other fields
```

### Provider Types

Two distinct provider types:

**AI Providers** - Create content (prompts, code, reviews):
```python
class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> ProviderResult | None:
        """Generate content from prompt."""
        ...
```

**Approval Providers** - Decide if content is acceptable:
```python
class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"

class ApprovalResult(BaseModel):
    decision: ApprovalDecision
    feedback: str | None = None  # Required if REJECTED

class ApprovalProvider(ABC):
    @abstractmethod
    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],  # filepath -> content (None if approver can read FS)
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Evaluate content and return approval decision.

        Single evaluation per attempt - no back-and-forth.
        """
        ...
```

**Design decisions for approval providers:**
- **Binary decisions only**: APPROVED or REJECTED. No "approved with changes" - if changes are needed, reject with feedback and let the AI provider regenerate.
- **Single evaluation**: Approver is called once per attempt. No iterative refinement between AI provider and approver.
- **Files as dict**: Approver receives `dict[str, str | None]` where keys are file paths and values are content. Value is `None` if the approver has filesystem access and should read the file directly.

### Built-in Approval Providers

| Provider | Behavior |
|----------|----------|
| `skip` | Auto-approve, no gate |
| `manual` | Pause workflow, require user `approve`/`reject` command |
| AI provider key | Delegate approval to AI (e.g., `gpt`, `claude`) |

### Configuration

```yaml
providers:
  plan:
    ai: gemini              # AI creates the plan
    approver: manual        # User approves plan
    max_retries: 3          # Max retries on rejection
  generate:
    ai: claude              # AI generates code
    approver: skip          # No approval gate (rely on review)
    max_retries: 3
  review:
    ai: gpt                 # AI reviews code
    approver: manual        # User approves review verdict
    max_retries: 3
  revise:
    ai: claude              # AI revises code
    approver: skip          # No approval gate
    max_retries: 3
```

### Commands

| Command | Purpose |
|---------|---------|
| `init` | Initialize workflow session |
| `step` | Advance workflow (enter next phase, trigger AI processing) |
| `approve` | Accept pending content, advance to next stage/phase |
| `reject` | Reject pending content with feedback (manual approver only) |
| `retry` | Re-invoke AI provider with feedback to regenerate content |
| `status` | Show current workflow state |
| `cancel` | Cancel workflow |

**Command semantics:**
- `approve` = "I accept this content as-is"
- `reject` = "I reject this content, halt workflow" (manual approver, no automatic retry)
- `retry` = "Regenerate with this feedback" (triggers AI provider again)

Note: `reject` without `retry` is only meaningful with manual approvers. With AI approvers, rejection always triggers retry (up to max_retries).

### Workflow Flow

```
init
  │
  ▼
PLAN[ING] ─── prompt created ───► [approval gate] ───► PLAN[ED]
  │                                                        │
  │ (AI called, response received)                         │
  │                                                        │
  ▼                                                        ▼
PLAN[ED] ─── plan ready ────────► [approval gate] ───► GENERATE[ING]
  │
  ▼
GENERATE[ING] ─── prompt created ► [approval gate] ───► GENERATE[ED]
  │                                                        │
  │ (AI called, code generated)                            │
  │                                                        │
  ▼                                                        ▼
GENERATE[ED] ─── code ready ─────► [approval gate] ───► REVIEW[ING]
  │
  ... continues through REVIEW and possibly REVISE ...
  │
  ▼
COMPLETE
```

### Approval Gate Behavior

At each approval gate:

1. **If approver is `skip`**: Auto-approve, continue immediately
2. **If approver is `manual`**: Pause workflow, set `pending_approval=True`
   - User calls `approve` → continue to next stage/phase
   - User calls `reject --feedback "..."` → halt workflow (user must `retry` or `cancel`)
   - User calls `retry --feedback "..."` → regenerate content with feedback
3. **If approver is AI provider**: Call AI approver with content and context
   - If `APPROVED` → continue to next stage/phase
   - If `REJECTED` → auto-retry with feedback (up to max_retries)
   - If max_retries exceeded → set ERROR status

### Stage Transitions

Within a phase, transitions happen automatically:

```
PHASE[ING] ──approve──► (call AI) ──► PHASE[ED] ──approve──► (next phase)
```

The `step` command enters a phase. Once in ING stage, approval triggers AI provider and moves to ED. Once in ED stage, approval moves to next phase's ING.

### Retry Flow

Retry behavior depends on the AI provider type:

**Automated AI provider (claude, gpt, gemini, etc.):**
- On rejection, automatically retry with feedback
- Retry prompt structure: original prompt + rejected output + approver feedback
- Continue until approved or max_retries exceeded
- If max_retries exceeded → ERROR status

**Manual AI provider:**
- On rejection, halt workflow (user must manually provide new content)
- User can edit content in place, then `approve`
- Or user can `cancel` the workflow

### Retry Prompt Structure

When retrying after rejection, the AI provider receives:

```
[Original Prompt]

---

The previous attempt was rejected. Here is the rejected output:

[Rejected Content]

---

Feedback from reviewer:

[Approver Feedback]

---

Please regenerate, addressing the feedback above.
```

### Hashing Behavior

Deferred hashing is preserved:

- **ING stage approval**: Hash prompt (if enabled), record approval
- **ED stage approval**: Hash response/artifacts, record approval
- Hashing occurs at approval time to capture any user edits

---

## File Changes

| File | Changes |
|------|---------|
| `aiwf/domain/models/workflow_state.py` | New `WorkflowStage` enum, update `WorkflowPhase` |
| `aiwf/domain/models/approval_result.py` | New `ApprovalDecision` enum, `ApprovalResult` model |
| `aiwf/domain/providers/approval_provider.py` | New `ApprovalProvider` ABC |
| `aiwf/domain/providers/approval_factory.py` | New factory for approval providers |
| `aiwf/application/workflow_orchestrator.py` | Refactor for phase+stage model, add `retry()` method |
| `aiwf/application/approval_handler.py` | Integrate approval providers |
| `aiwf/interface/cli/cli.py` | Add `reject` and `retry` commands |
| Configuration schema | New provider config structure with `ai`, `approver`, `max_retries` per phase |

---

## Migration Strategy

This is a breaking change. Migration approach:

1. Create new models alongside existing
2. Add migration utility to convert old sessions
3. Deprecate old phase enum values
4. Remove old code after transition period

Alternatively, treat v2.0 as a clean break with no migration (acceptable for pre-1.0 software).

---

## Consequences

### Positive

1. **Clear mental model**: 4 phases with 2 stages is easier to understand than 10+ phases
2. **Flexible automation**: Any combination of manual/AI approval per phase-stage
3. **Separation of concerns**: AI creates, approvers evaluate
4. **Extensible**: Custom approval providers without engine changes
5. **Better UX**: Fewer commands for common workflows
6. **AI-to-AI workflows**: AI generates, different AI approves

### Negative

1. **Breaking change**: Existing sessions incompatible
2. **More configuration**: Users must configure more providers
3. **Complexity**: More abstractions (stages, approval providers)
4. **Testing surface**: More combinations to test

---

## Alternatives Considered

### Keep Current Model, Fix Implementation

**Rejected**: The fundamental issue is the phase model itself. Fixing implementation without changing the model would still leave confusing semantics.

### Approval as Profile Responsibility

**Rejected**: Puts too much responsibility in profiles. Approval is orthogonal to content generation and should be independently configurable.

### Single Provider Per Phase

**Rejected**: Loses flexibility of having different AI for creation vs approval.

---

## Related Decisions

- ADR-0001: Architecture Overview (superseded in part)
- ADR-0005: Chain of Responsibility (may need updates)
- ADR-0007: Plugin Architecture (approval providers extend this)

---

## Resolved Design Decisions

These questions were raised during design discussions and have been resolved:

### 1. Should prompt approval be a separate gate from response approval?

**Decision:** Separate gates. Each phase has an ING stage (prompt/input) and ED stage (response/output), each with its own approval gate. This allows flexibility: some workflows may want to approve prompts but auto-approve outputs, or vice versa.

### 2. How should approval providers access artifacts?

**Decision:** Approvers receive `files: dict[str, str | None]`. Keys are file paths, values are content. If the approver has filesystem access (e.g., local AI tool), value can be `None` and the approver reads directly. This supports both API-based approvers (need content passed) and local tools (can read FS).

### 3. Should we support approval provider chains?

**Decision:** No, not in v1. Single approver per phase-stage. Chains add complexity without clear use case. Can be added later if needed.

### 4. What context should be passed to approval providers?

**Decision:** Approvers receive:
- `phase`: Current workflow phase (PLAN, GENERATE, etc.)
- `stage`: Current stage (ING or ED)
- `files`: Dict of filepath → content
- `context`: Dict with session metadata, iteration number, prior phase outputs

### 5. Should approvers be able to make changes?

**Decision:** No. Binary APPROVED/REJECTED only. If changes needed, reject with feedback and let AI provider regenerate. "Approved with changes" was rejected as too complex for v1, and the iterative regeneration loop achieves the same goal.

### 6. What happens on rejection with different provider types?

**Decision:**
- AI provider + AI approver → auto-retry with feedback (up to max_retries)
- AI provider + manual approver → pause for user (user can `approve`, `reject`, or `retry`)
- Manual provider + any approver → pause for user (user must provide new content)

---

## Appendix: Example Workflows

### Fully Manual (Interactive Mode)

```yaml
providers:
  plan: { ai: manual, approver: manual }
  generate: { ai: manual, approver: manual }
  review: { ai: manual, approver: manual }
  revise: { ai: manual, approver: manual }
```

User copies prompts to AI chat, pastes responses, calls approve at each step. Maximum control, minimum automation.

### Fully Automated

```yaml
providers:
  plan: { ai: claude, approver: skip }
  generate: { ai: claude, approver: skip }
  review: { ai: claude, approver: skip }
  revise: { ai: claude, approver: skip }
```

Single `step` command runs entire workflow. No human intervention required.

### Human-in-the-Loop Code Review (Interactive Mode)

```yaml
providers:
  plan: { ai: claude, approver: skip }
  generate: { ai: claude, approver: skip }
  review: { ai: gpt, approver: manual }  # User reviews the review
  revise: { ai: claude, approver: skip }
```

AI generates plan and code automatically. Workflow pauses at REVIEW[ED] for user to approve the review verdict before revision. **This is an interactive workflow** because it requires human approval at the review phase.

### AI-to-AI Validation (Fully Automated)

```yaml
providers:
  plan: { ai: gemini, approver: gpt }     # GPT validates Gemini's plan
  generate: { ai: claude, approver: gemini }  # Gemini validates Claude's code
  review: { ai: gpt, approver: claude }   # Claude validates GPT's review
  revise: { ai: claude, approver: skip }
```

Different AIs create and validate each other's work. No human intervention required. If any approver rejects, the creating AI retries with feedback.

---

## Appendix: Provider Combination Matrix

| AI Provider | Approver | Mode | Rejection Behavior |
|-------------|----------|------|-------------------|
| Manual | Skip | Interactive | N/A (auto-approved) |
| Manual | Manual | Interactive | User edits content, then approves |
| Manual | AI | Interactive | User edits content based on AI feedback |
| Automated | Skip | Automated | N/A (auto-approved) |
| Automated | AI | Automated | Auto-retry with feedback (up to max_retries) |
| Automated | Manual | **Invalid** | Contradicts automated mode |

The "Automated + Manual" combination is invalid because requiring human approval makes the workflow interactive by definition.
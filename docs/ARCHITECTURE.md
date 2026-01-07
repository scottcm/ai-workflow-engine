# AI Workflow Engine Architecture

## Purpose

The AI Workflow Engine orchestrates multi-phase, AI-assisted code generation workflows. It provides a framework where:

1. **Profiles** define domain-specific workflows (e.g., JPA entity generation)
2. **AI Providers** execute prompts (manual or automated)
3. **The Engine** manages state transitions, file I/O, and approval gates

The engine is designed to work in both **manual mode** (user copies prompts to AI tools, pastes responses back) and **automated mode** (providers call AI APIs directly).

### Core Value Proposition

- **Structured workflow** with defined phases (plan → generate → review → revise)
- **Quality gates** at each step with approval/rejection flow
- **Iteration support** for revision cycles
- **Profile-based extensibility** for different code generation domains

---

## System Design

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Interface Layer (CLI)                     │
│                   aiwf/interface/cli/                        │
├─────────────────────────────────────────────────────────────┤
│                  Application Layer (Engine)                  │
│  WorkflowOrchestrator, TransitionTable, ApprovalConfig       │
│                  aiwf/application/                           │
├─────────────────────────────────────────────────────────────┤
│                     Domain Layer                             │
│   Profiles, Providers, Models, Persistence, Standards        │
│                     aiwf/domain/                             │
├─────────────────────────────────────────────────────────────┤
│               External Profiles (pluggable)                  │
│                     profiles/                                │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Why | Reference |
|----------|-----|-----------|
| Phase+Stage model | Clear state transitions, explicit approval points | ADR-0012 |
| TransitionTable | Declarative state machine, easy to verify | ADR-0012 |
| Profiles never do I/O | Testability, clear responsibility boundary | ADR-0001 |
| Engine executes WritePlan | Single point of file management | ADR-0001 |
| Approval gates post-creation | Gates evaluate content, not permissions | ADR-0015 |

---

## Design Patterns

### Strategy Pattern: Profiles and Providers

The system uses Strategy pattern for pluggable behaviors:

```
┌──────────────────┐     ┌───────────────────┐
│ WorkflowProfile  │     │   AIProvider      │
│     (ABC)        │     │     (ABC)         │
├──────────────────┤     ├───────────────────┤
│ generate_*_prompt│     │ validate()        │
│ process_*_response│    │ generate()        │
└────────┬─────────┘     └────────┬──────────┘
         │                        │
    ┌────┴────┐              ┌────┴────┐
    │JpaMtProfile│           │ManualAI │  │ClaudeCode│
    └──────────┘             └─────────┘  └──────────┘
```

**Profiles** define domain-specific prompt generation and response parsing. They receive content strings and return data structures - no I/O.

**Providers** handle AI communication, file reading, and may write files directly (local-write capability). They receive file paths and perform I/O as needed.

### Factory Pattern: Registration and Discovery

Factories enable runtime registration and lookup:

```python
# Registration (plugin startup)
ProfileFactory.register("jpa-mt", JpaMtProfile)
AIProviderFactory.register("claude-code", ClaudeCodeAIProvider)

# Usage (engine)
profile = ProfileFactory.create("jpa-mt")
provider = AIProviderFactory.create("claude-code")
```

### State Machine: TransitionTable

A declarative table-driven state machine:

```python
# Key: (phase, stage, command) → TransitionResult(phase, stage, action)
_TRANSITIONS = {
    (INIT, None, "init"): TransitionResult(PLAN, PROMPT, CREATE_PROMPT),
    (PLAN, PROMPT, "approve"): TransitionResult(PLAN, RESPONSE, CALL_AI),
    (PLAN, RESPONSE, "approve"): TransitionResult(GENERATE, PROMPT, CREATE_PROMPT),
    # ... etc
}
```

Benefits:
- All valid transitions visible in one place
- Easy to verify completeness
- New phases/stages = add rows, not code

### Double Dispatch: Approval Handlers

Phase-specific approval logic without if/else chains:

```python
_APPROVAL_HANDLERS = {
    (PLAN, RESPONSE): "_approve_plan_response",
    (GENERATE, RESPONSE): "_approve_generate_response",
    # ...
}

def _handle_pre_transition_approval(self, state, session_dir):
    handler_name = self._APPROVAL_HANDLERS.get((state.phase, state.stage))
    if handler_name:
        handler = getattr(self, handler_name)
        handler(state, session_dir)
```

---

## Core Abstractions

### WorkflowState

The complete state snapshot of a workflow session:

```python
class WorkflowState(BaseModel):
    # Identity
    session_id: str
    profile: str

    # State machine position
    phase: WorkflowPhase      # INIT, PLAN, GENERATE, REVIEW, REVISE, COMPLETE
    stage: WorkflowStage      # PROMPT or RESPONSE (None for terminal states)
    status: WorkflowStatus    # IN_PROGRESS, SUCCESS, FAILED, ERROR, CANCELLED

    # Iteration tracking (1-based, increments on revision)
    current_iteration: int

    # Profile-specific data lives here, NOT as top-level fields
    context: dict[str, Any]

    # Provider configuration
    ai_providers: dict[str, str]  # role → provider_key
```

### ProcessingResult

What profiles return from response processing:

```python
class ProcessingResult(BaseModel):
    status: WorkflowStatus
    write_plan: WritePlan | None  # Files for engine to write
    metadata: dict[str, Any]      # Phase-specific data (e.g., verdict)
```

### WritePlan / WriteOp

How profiles request file writes:

```python
class WriteOp(BaseModel):
    path: str      # Filename only or relative path
    content: str   # File contents

class WritePlan(BaseModel):
    writes: list[WriteOp]
```

**Contract**: Profiles return filename-only paths. Engine adds `iteration-{N}/code/` prefix.

### ApprovalResult

What approval providers return:

```python
class ApprovalResult(BaseModel):
    decision: ApprovalDecision  # APPROVED, REJECTED, PENDING
    feedback: str | None        # Rejection reason or instructions
    suggested_content: str | None  # Optional rewrite suggestion
```

---

## Workflow Flow

### Phase Progression

```
INIT → PLAN → GENERATE → REVIEW → COMPLETE
                  ↑          │
                  └── REVISE ←┘ (on FAIL verdict)
```

### Stage Model (within each phase)

```
PROMPT stage                    RESPONSE stage
┌─────────────────┐            ┌─────────────────┐
│ Profile creates │  approve   │ AI generates    │  approve
│ prompt file     │ ────────→  │ response file   │ ────────→ next phase
│                 │            │                 │
│ Gate runs       │            │ Gate runs       │
│ (post-creation) │            │ (post-creation) │
└─────────────────┘            └─────────────────┘
```

**Key insight**: Gates run AFTER content creation. The `approve` command resolves a pending gate, not initiates one.

### Approval Gate Flow

```
1. Engine calls profile.generate_*_prompt() or provider.generate()
2. Engine writes file
3. Engine calls _run_gate_after_action()
4. Approver.evaluate() returns:
   - APPROVED → auto-continue to next stage
   - PENDING → set pending_approval=True, pause workflow
   - REJECTED → retry or pause for user intervention
5. If paused, user runs `approve` or `reject` command to continue
```

---

## Responsibility Boundaries

### What Profiles Do

| Responsibility | Method |
|---------------|--------|
| Generate prompts | `generate_{phase}_prompt()` |
| Parse responses | `process_{phase}_response()` |
| Return WritePlan | Via ProcessingResult |
| Define context schema | `get_metadata()["context_schema"]` |
| Configure standards | `get_standards_config()` |

### What Profiles DON'T Do

- File I/O (reading/writing files)
- Mutate WorkflowState
- Make state transition decisions
- Call AI providers directly

### What the Engine Does

| Responsibility | Location |
|---------------|----------|
| State transitions | TransitionTable + orchestrator |
| Execute WritePlan | `_approve_*_response()` handlers |
| Run approval gates | `_run_gate_after_action()` |
| Manage sessions | SessionStore |
| Compute file hashes | approval handlers |

### What Providers Do

| Type | Responsibility |
|------|---------------|
| AIProvider | Accept prompt, return response (or None for manual). May read/write files. |
| ApprovalProvider | Evaluate content, return APPROVED/REJECTED/PENDING. May read files. |
| StandardsProvider | Create standards bundle from sources. May read files. |

**Note**: Providers often receive file paths rather than content, so they perform I/O as needed. This is different from profiles, which receive content strings and never do I/O.

**AIProvider → ApprovalProvider Adapter**: Any AIProvider can be used as an approval provider via `AIApprovalProvider` adapter. This allows using Claude, Gemini, etc. for automated approval gates.

---

## Session File Structure

```
.aiwf/sessions/{session-id}/
├── state.json              # WorkflowState snapshot
├── standards-bundle.md     # Materialized standards
├── plan.md                 # Approved plan (copied from iteration-1)
└── iteration-{N}/
    ├── planning-prompt.md
    ├── planning-response.md
    ├── generation-prompt.md
    ├── generation-response.md
    ├── review-prompt.md
    ├── review-response.md
    ├── revision-prompt.md    # Only if revision needed
    ├── revision-response.md
    └── code/
        └── {generated files}
```

---

## Extension Points

### Adding a New Profile

1. Create class implementing `WorkflowProfile` ABC
2. Implement all abstract methods
3. Register with `ProfileFactory.register("key", MyProfile)`
4. Optionally add CLI commands via `register(cli_group)` entry point

### Adding a New AI Provider

1. Create class implementing `AIProvider` ABC
2. Implement `validate()` and `generate()`
3. Register with `AIProviderFactory.register("key", MyProvider)`

### Adding a New Approval Provider

1. Create class implementing `ApprovalProvider` ABC
2. Implement `evaluate()` returning ApprovalResult
3. Register with `ApprovalProviderFactory.register("key", MyApprover)`

**Shortcut**: Wrap any existing AIProvider with `AIApprovalProvider` adapter to use it for approval gates without implementing ApprovalProvider directly.

---

## System Invariants

These must always hold:

1. **Profiles never do I/O** - They receive content strings, return ProcessingResult/WritePlan
2. **Engine writes all files** - Single point of file management, consistent paths
3. **State transitions are explicit** - All in TransitionTable, no hidden transitions
4. **Gates run post-creation** - Content exists before approval evaluation
5. **Context isolates profile data** - Profile-specific fields in `context` dict, not WorkflowState
6. **Iterations are 1-based** - First iteration is `iteration-1`

---

## ADR Summary

| ADR | Status | Key Decision |
|-----|--------|--------------|
| 0001 | Accepted | Strategy + Factory patterns, clear boundaries |
| 0002 | Accepted | Template layering with `{{include:}}` |
| 0003 | Accepted | Pydantic for all models |
| 0004 | Accepted | `@@@REVIEW_META` structured metadata |
| 0012 | Accepted | Phase+Stage model, TransitionTable |
| 0013 | Accepted | Claude Code provider via Agent SDK |
| 0015 | Accepted | Three-state approval (APPROVED/REJECTED/PENDING) |

See `docs/adr/` for full decision records.

---

## Implementation Notes

<!-- Patterns, gotchas, and learnings discovered during implementation. -->

### Scope Filtering

- Scope filtering is **layer-specific**, not cumulative
- Each scope explicitly lists its files and prefix filters
- Empty prefixes list = include all rules from specified files

### Provider vs Profile I/O

- Providers receive file paths, perform I/O as needed
- Profiles receive content strings, never do I/O
- This distinction is critical for testability

### AI Provider Return Types (v2)

- `AIProvider.generate()` returns `AIProviderResult | None`
- `None` = manual provider (user writes response file)
- `AIProviderResult` = automated provider (engine writes response)
- No legacy string return - v2 is not backward compatible

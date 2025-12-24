# ADR-0005: Chain of Responsibility for Approval Handling

**Status:** Proposed  
**Date:** December 24, 2024  
**Deciders:** Scott

---

## Context and Problem Statement

The current `ApprovalHandler.approve()` method is a monolithic 150+ line function with branching logic that handles all approval scenarios:

- ING phases (PLANNING, GENERATING, REVIEWING, REVISING): Call providers, write responses
- ED phases (PLANNED, GENERATED, REVIEWED, REVISED): Hash artifacts, set approval flags

This structure has several problems:

1. **Modification risk** — Adding new phase types or approval logic requires editing a large, complex method
2. **Testing difficulty** — Each approval path cannot be tested in isolation
3. **Violation of Open/Closed Principle** — The handler must be modified to extend behavior
4. **Code navigation** — Understanding what happens for a specific phase requires reading the entire method

The existing `ING_APPROVAL_SPECS` and `ED_APPROVAL_SPECS` mappings in `approval_specs.py` already suggest a natural decomposition, but the handler doesn't leverage this structure.

---

## Decision Drivers

1. Each approval type should be independently testable
2. Adding new approval logic should not require modifying existing handlers
3. Clear separation of concerns between phase categories
4. Maintain existing behavior exactly (refactor, not rewrite)
5. Support future extension points (e.g., custom profile approval hooks)

---

## Considered Options

### Option 1: Keep Monolithic Handler

**Pros:**
- No refactoring effort
- Single place to see all logic

**Cons:**
- All problems listed above remain
- Technical debt increases with each addition

**Verdict:** ❌ Rejected

---

### Option 2: Strategy Pattern (Phase-Keyed Handlers)

**Pros:**
- Simple dictionary dispatch
- Each phase gets its own handler

**Cons:**
- Doesn't handle shared logic between similar phases (all ING phases share provider-calling logic)
- Would duplicate code across PLANNING/GENERATING/REVIEWING/REVISING handlers

**Verdict:** ⚠️ Rejected — too granular

---

### Option 3: Chain of Responsibility (Chosen)

**Pros:**
- Handlers can share base behavior (ING vs ED)
- Each handler decides if it can process the request
- New handlers added without modifying existing ones
- Natural fit for "try this, then try that" approval flow

**Cons:**
- Slightly more complex than direct dispatch
- Chain ordering matters

**Verdict:** ✅ Accepted

---

## Decision Outcome

Refactor `ApprovalHandler` to use Chain of Responsibility pattern with handler classes for each approval category.

---

## Architecture

### Handler Interface

```python
class ApprovalHandlerBase(ABC):
    """Base class for approval handlers."""
    
    def __init__(self, successor: ApprovalHandlerBase | None = None):
        self._successor = successor
    
    @abstractmethod
    def can_handle(self, state: WorkflowState) -> bool:
        """Return True if this handler can process the given state."""
        ...
    
    @abstractmethod
    def handle(self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool) -> WorkflowState:
        """Process approval for the given state."""
        ...
    
    def approve(self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool) -> WorkflowState:
        """Chain method: handle if possible, otherwise delegate to successor."""
        if self.can_handle(state):
            return self.handle(session_dir=session_dir, state=state, hash_prompts=hash_prompts)
        if self._successor:
            return self._successor.approve(session_dir=session_dir, state=state, hash_prompts=hash_prompts)
        raise ValueError(f"No handler found for phase: {state.phase}")
```

### Concrete Handlers

```python
class IngPhaseApprovalHandler(ApprovalHandlerBase):
    """Handles ING phases: PLANNING, GENERATING, REVIEWING, REVISING.
    
    Responsibility: Read prompt, call provider, write response.
    """
    
    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase in ING_APPROVAL_SPECS


class PlannedApprovalHandler(ApprovalHandlerBase):
    """Handles PLANNED phase.
    
    Responsibility: Copy planning-response to plan.md, hash, set plan_approved.
    """
    
    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase == WorkflowPhase.PLANNED


class CodeArtifactApprovalHandler(ApprovalHandlerBase):
    """Handles GENERATED and REVISED phases.
    
    Responsibility: Hash code files, create/update Artifact records.
    """
    
    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase in {WorkflowPhase.GENERATED, WorkflowPhase.REVISED}


class ReviewedApprovalHandler(ApprovalHandlerBase):
    """Handles REVIEWED phase.
    
    Responsibility: Hash review response, set review_approved.
    """
    
    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase == WorkflowPhase.REVIEWED
```

### Chain Assembly

```python
def build_approval_chain() -> ApprovalHandlerBase:
    """Build the standard approval handler chain."""
    # Chain order: most specific first, catch-all last
    reviewed = ReviewedApprovalHandler()
    code_artifact = CodeArtifactApprovalHandler(successor=reviewed)
    planned = PlannedApprovalHandler(successor=code_artifact)
    ing = IngPhaseApprovalHandler(successor=planned)
    return ing
```

### Orchestrator Integration

```python
class WorkflowOrchestrator:
    def __init__(self, ...):
        ...
        self._approval_chain = build_approval_chain()
    
    def approve(self, session_id: str, hash_prompts: bool = False) -> WorkflowState:
        state = self.session_store.load(session_id)
        session_dir = self.sessions_root / session_id
        
        updated = self._approval_chain.approve(
            session_dir=session_dir,
            state=state,
            hash_prompts=hash_prompts,
        )
        
        self.session_store.save(updated)
        return updated
```

---

## File Changes

| File | Changes |
|------|---------|
| `aiwf/application/approval_handler.py` | Refactor to handler classes |
| `aiwf/application/workflow_orchestrator.py` | Use chain instead of direct ApprovalHandler |
| `tests/unit/application/test_approval_handler.py` | Test each handler in isolation |

---

## Consequences

### Positive

1. **Testability** — Each handler tested independently with minimal setup
2. **Extensibility** — New phases or approval types added as new handlers
3. **Clarity** — Handler responsibility is explicit in class name and can_handle()
4. **Maintainability** — Changes to PLANNED approval don't risk breaking REVIEWED approval

### Negative

1. **More files/classes** — Four handler classes instead of one method
2. **Chain ordering** — Must ensure chain is assembled correctly
3. **Indirection** — Slightly harder to trace full approval flow

---

## Migration Strategy

1. Create handler classes with logic extracted from current `approve()` method
2. Add tests for each handler in isolation
3. Replace `ApprovalHandler.approve()` with chain delegation
4. Verify all existing tests pass
5. Remove old monolithic logic

---

## Related Decisions

- ADR-0001: Architecture Overview (defines approval semantics)
- ADR-0006: Observer Pattern for Events (handlers may emit events)


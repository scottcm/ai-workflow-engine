# ADR-0006: Observer Pattern for Workflow Events

**Status:** Accepted
**Date:** December 24, 2024 (Updated: December 25, 2024)
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine is designed to support external integrations, particularly:

- VS Code extension (primary consumer)
- IntelliJ plugin (primary consumer)
- Future: webhooks, logging systems, metrics collectors

Currently, integrations must **poll** for state changes:

```typescript
// IDE extension must poll
while (true) {
    const status = await execAiwf(['status', sessionId]);
    if (status.phase !== lastPhase) {
        // React to change
    }
    await sleep(1000);
}
```

This approach has significant drawbacks:

1. **Latency** — Changes detected only at poll interval
2. **Overhead** — Constant subprocess spawning and JSON parsing
3. **Complexity** — Extension must track "last known state" and diff
4. **No granularity** — Can't distinguish "artifact created" from "phase changed"

The engine needs a way to **notify** integrations when significant events occur.

---

## Decision Drivers

1. Extensions should be reactive, not poll-based
2. Event system must not couple engine to specific consumers
3. Support both in-process (library) and out-of-process (CLI) consumers
4. Enable future capabilities: webhooks, audit logging, metrics
5. Minimal performance impact when no observers registered

---

## Considered Options

### Option 1: Callback Registration

**Pros:**
- Simple to implement
- Direct function calls

**Cons:**
- Tight coupling between emitter and listener
- No support for out-of-process consumers
- Callbacks can throw, affecting workflow

**Verdict:** ❌ Rejected

---

### Option 2: Event Bus / Pub-Sub

**Pros:**
- Full decoupling
- Supports multiple listeners
- Can add persistence, replay

**Cons:**
- Over-engineered for current needs
- Requires additional infrastructure

**Verdict:** ⚠️ Rejected for now — consider for distributed scenarios

---

### Option 3: Observer Pattern with Event Emitter (Chosen)

**Pros:**
- Clean separation between emitter and observers
- Supports multiple listeners per event type
- Lightweight implementation
- Standard pattern, well understood

**Cons:**
- In-process only (CLI needs separate mechanism)
- Observers must not throw or block

**Verdict:** ✅ Accepted

---

## Decision Outcome

Implement Observer pattern with a `WorkflowEventEmitter` that supports typed events and multiple observers.

For CLI consumers, emit events as structured lines to stderr (compatible with progress messaging).

---

## Architecture

### Event Types

**Implementation Note:** The final implementation emits events only **after** transitions complete, not before. This simplifies the event model and avoids confusion about partial state.

```python
class WorkflowEventType(str, Enum):
    """Typed workflow events."""

    # Phase lifecycle (emit after transition completes)
    PHASE_ENTERED = "phase_entered"        # Entered phase

    # Artifacts
    ARTIFACT_CREATED = "artifact_created"  # File written to session
    ARTIFACT_APPROVED = "artifact_approved"  # Hash computed, artifact finalized

    # Approval gates
    APPROVAL_REQUIRED = "approval_required"  # Workflow blocked pending approval
    APPROVAL_GRANTED = "approval_granted"    # User approved, workflow can continue

    # Workflow lifecycle
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"

    # Iteration
    ITERATION_STARTED = "iteration_started"  # New revision iteration began
```

**Omitted Events:**
- `PHASE_ENTERING` — Removed. Emit only after transition completes.
- `WORKFLOW_STARTED` — Removed. Initialization is synchronous; no observer context yet.

### Event Payload

**Implementation Note:** Uses Pydantic `BaseModel` for consistency with the rest of the codebase (not `@dataclass`).

```python
from pydantic import BaseModel, Field

class WorkflowEvent(BaseModel):
    """Immutable event payload."""

    model_config = {"frozen": True}

    event_type: WorkflowEventType
    session_id: str
    timestamp: datetime
    phase: WorkflowPhase | None = None
    iteration: int | None = None
    artifact_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Observer Interface

```python
class WorkflowObserver(Protocol):
    """Protocol for workflow event observers."""
    
    def on_event(self, event: WorkflowEvent) -> None:
        """Handle a workflow event. Must not throw or block."""
        ...
```

### Event Emitter

```python
class WorkflowEventEmitter:
    """Central event dispatcher for workflow events."""
    
    def __init__(self):
        self._observers: dict[WorkflowEventType, list[WorkflowObserver]] = defaultdict(list)
        self._global_observers: list[WorkflowObserver] = []
    
    def subscribe(
        self, 
        observer: WorkflowObserver, 
        event_types: list[WorkflowEventType] | None = None
    ) -> None:
        """Subscribe to specific event types, or all events if None."""
        if event_types is None:
            self._global_observers.append(observer)
        else:
            for event_type in event_types:
                self._observers[event_type].append(observer)
    
    def unsubscribe(self, observer: WorkflowObserver) -> None:
        """Remove observer from all subscriptions."""
        if observer in self._global_observers:
            self._global_observers.remove(observer)
        for observers in self._observers.values():
            if observer in observers:
                observers.remove(observer)
    
    def emit(self, event: WorkflowEvent) -> None:
        """Dispatch event to all relevant observers."""
        # Global observers first
        for observer in self._global_observers:
            self._safe_notify(observer, event)
        
        # Type-specific observers
        for observer in self._observers.get(event.event_type, []):
            self._safe_notify(observer, event)
    
    def _safe_notify(self, observer: WorkflowObserver, event: WorkflowEvent) -> None:
        """Notify observer, catching and logging any exceptions."""
        try:
            observer.on_event(event)
        except Exception as e:
            # Log but don't propagate — observers must not break workflow
            logger.warning(f"Observer {observer} failed on {event.event_type}: {e}")
```

### Orchestrator Integration

```python
class WorkflowOrchestrator:
    def __init__(
        self, 
        session_store: SessionStore, 
        sessions_root: Path,
        event_emitter: WorkflowEventEmitter | None = None,
    ):
        self.session_store = session_store
        self.sessions_root = sessions_root
        self._events = event_emitter or WorkflowEventEmitter()
    
    def _emit(self, event_type: WorkflowEventType, state: WorkflowState, **kwargs) -> None:
        """Helper to emit events with common fields."""
        self._events.emit(WorkflowEvent(
            event_type=event_type,
            session_id=state.session_id,
            timestamp=datetime.now(timezone.utc),
            phase=state.phase,
            iteration=state.current_iteration,
            **kwargs,
        ))
    
    def step(self, session_id: str) -> WorkflowState:
        state = self.session_store.load(session_id)
        old_phase = state.phase
        
        # ... do work ...
        
        if state.phase != old_phase:
            self._emit(WorkflowEventType.PHASE_ENTERED, state)
        
        return state
```

---

## CLI Integration

For out-of-process consumers (IDE extensions via CLI), events are emitted as structured stderr lines **when the `--events` flag is provided**:

```bash
$ aiwf step abc123 --events
[EVENT] phase_entered phase=GENERATING iteration=1
[EVENT] artifact_created path=iteration-1/code/Entity.java
{"exit_code":0,"session_id":"abc123",...}
```

**Implementation Note:** The `--events` flag is opt-in to keep stderr clean for manual users. IDEs should always include this flag.

The extension can parse stderr for `[EVENT]` lines while reading JSON from stdout.

### CLI Observer

```python
class StderrEventObserver:
    """Emits events as structured lines to stderr."""

    def on_event(self, event: WorkflowEvent) -> None:
        parts = [f"[EVENT] {event.event_type.value}"]
        if event.phase:
            parts.append(f"phase={event.phase.name}")
        if event.iteration is not None:  # Include 0
            parts.append(f"iteration={event.iteration}")
        if event.artifact_path:
            parts.append(f"path={event.artifact_path}")
        click.echo(" ".join(parts), err=True)
```

### CLI Command Changes

Both `step` and `approve` commands accept `--events`:

```bash
$ aiwf step --help
Usage: aiwf step [OPTIONS] SESSION_ID

Options:
  --events  Emit workflow events to stderr.
  --help    Show this message and exit.

$ aiwf approve --help
Usage: aiwf approve [OPTIONS] SESSION_ID

Options:
  --hash-prompts     Hash prompts.
  --no-hash-prompts  Do not hash prompts.
  --events           Emit workflow events to stderr.
  --help             Show this message and exit.
```

---

## Example: IDE Extension Usage

```typescript
// In-process usage (if engine used as library)
const emitter = orchestrator.eventEmitter;
emitter.subscribe({
    onEvent: (event) => {
        if (event.eventType === 'artifact_created') {
            showNotification(`Created: ${event.artifactPath}`);
        }
    }
});

// CLI usage (parsing stderr) - works for VS Code, IntelliJ, or any IDE
const proc = spawn('aiwf', ['step', sessionId]);
proc.stderr.on('data', (data) => {
    const lines = data.toString().split('\n');
    for (const line of lines) {
        if (line.startsWith('[EVENT]')) {
            const event = parseEventLine(line);
            handleEvent(event);
        }
    }
});
```

---

## File Changes

| File | Changes |
|------|---------|
| `aiwf/domain/events/__init__.py` | New: Package exports |
| `aiwf/domain/events/event_types.py` | New: WorkflowEventType enum (8 event types) |
| `aiwf/domain/events/event.py` | New: WorkflowEvent Pydantic model |
| `aiwf/domain/events/emitter.py` | New: WorkflowEventEmitter |
| `aiwf/domain/events/observer.py` | New: WorkflowObserver protocol |
| `aiwf/domain/events/stderr_observer.py` | New: StderrEventObserver for CLI |
| `aiwf/application/workflow_orchestrator.py` | Add event_emitter parameter, _emit() helper, emit at transitions |
| `aiwf/interface/cli/cli.py` | Add --events flag to step and approve commands |
| `tests/unit/domain/events/test_event_types.py` | New: Event type tests |
| `tests/unit/domain/events/test_event.py` | New: Event model tests |
| `tests/unit/domain/events/test_observer.py` | New: Observer protocol tests |
| `tests/unit/domain/events/test_emitter.py` | New: Emitter tests |
| `tests/unit/domain/events/test_stderr_observer.py` | New: Stderr observer tests |
| `tests/unit/application/test_workflow_orchestrator_events.py` | New: Orchestrator event emission tests |

---

## Consequences

### Positive

1. **Reactive integrations** — Extensions notified immediately on changes
2. **Decoupling** — Engine doesn't know about specific consumers
3. **Extensibility** — Add webhooks, metrics, logging as observers
4. **Debugging** — Events provide audit trail of workflow execution
5. **Portfolio value** — Demonstrates understanding of enterprise patterns

### Negative

1. **Complexity** — More moving parts than simple return values
2. **Error handling** — Observers must not throw; requires defensive coding
3. **Testing** — Must test event emission alongside behavior
4. **CLI overhead** — Parsing stderr adds complexity to IDE extensions

---

## Future Extensions

1. **Event persistence** — Store events for replay/debugging
2. **Webhook observer** — POST events to configured URLs
3. **Metrics observer** — Emit Prometheus/StatsD metrics
4. **Event filtering** — Subscribe to events matching criteria

---

## Related Decisions

- ADR-0001: Architecture Overview
- ADR-0005: Chain of Responsibility for Approval (handlers emit events)


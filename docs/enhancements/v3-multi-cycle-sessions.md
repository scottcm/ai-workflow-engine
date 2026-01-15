# Enhancement: v3 Multi-Cycle Sessions

**Status:** Draft
**Date:** January 15, 2026
**Author:** Scott

---

## Context and Problem Statement

The v2.x engine runs a single phase cycle (PLAN → GENERATE → REVIEW → REVISE) per session. This creates limitations:

1. **Token budget pressure** - Large scopes like `full` require all standards in one prompt
2. **All-or-nothing generation** - Can't iterate on domain layer independently from API layer
3. **Separate sessions for tests** - Must manually link test sessions to code sessions
4. **Flat directory structure** - All iterations mixed in `iteration-{N}/` regardless of purpose

v3 introduces **multi-cycle sessions** where a single session can execute multiple phase cycles, each producing different output types.

---

## Decision Drivers

1. **Token efficiency** - Smaller, focused prompts per cycle
2. **Independent iteration** - Revise domain without regenerating service/api
3. **Integrated test generation** - `--with-tests` flag runs tests cycle after code
4. **Clear organization** - Output organized by type, not just iteration number
5. **Profile flexibility** - Profiles declare what cycles they need
6. **Backward compatibility** - v2.x patterns (session linking) continue to work

---

## Proposed Solution

### Multi-Cycle Session Model

A session contains one or more **cycles**. Each cycle:
- Has a **type** (profile-provided string, e.g., `domain`, `service`, `api`, `tests`)
- Runs the full phase sequence: PLAN → GENERATE → REVIEW → [REVISE]
- Has its own iteration counter (for revisions within that cycle)
- Produces output in a type-specific directory

```
Session
├── Cycle 1: domain
│   └── PLAN → GENERATE → REVIEW → COMPLETE
├── Cycle 2: service
│   └── PLAN → GENERATE → REVIEW → COMPLETE
├── Cycle 3: api
│   └── PLAN → GENERATE → REVIEW → COMPLETE
└── Cycle 4: tests
    └── PLAN → GENERATE → REVIEW → COMPLETE
```

### Directory Structure

```
.aiwf/sessions/<session-id>/
├── domain/
│   ├── iteration-1/
│   │   ├── prompts/
│   │   ├── responses/
│   │   └── code/
│   └── iteration-2/          # If revision needed
├── service/
│   └── iteration-1/
├── api/
│   └── iteration-1/
└── tests/
    └── iteration-1/
```

Each type directory is independent. Revising `domain` (creating `domain/iteration-2/`) doesn't affect `service/iteration-1/`.

### Profile Interface

Profiles declare cycles via a new method:

```python
class WorkflowProfile(ABC):

    @abstractmethod
    def get_cycles(self, context: dict) -> list[CycleConfig]:
        """
        Return ordered list of cycles for this workflow.

        Called once at session initialization. Engine executes
        cycles in order, each running full phase sequence.
        """
        pass

@dataclass
class CycleConfig:
    type: str           # Directory name, e.g., "domain", "tests"
    scope: str          # Scope for this cycle's generation
    depends_on: list[str] = field(default_factory=list)  # Previous cycle types required
```

**Example implementations:**

```python
# jpa-mt profile

def get_cycles(self, context: dict) -> list[CycleConfig]:
    scope = context.get("scope")
    with_tests = context.get("with_tests", False)

    if scope == "domain":
        cycles = [CycleConfig(type="domain", scope="domain")]
    elif scope == "service":
        cycles = [CycleConfig(type="service", scope="service")]
    elif scope == "api":
        cycles = [CycleConfig(type="api", scope="api")]
    elif scope == "full":
        cycles = [
            CycleConfig(type="domain", scope="domain"),
            CycleConfig(type="service", scope="service", depends_on=["domain"]),
            CycleConfig(type="api", scope="api", depends_on=["service"]),
        ]
    elif scope == "tests":
        # v2.x compatibility: tests from source session/files
        cycles = [CycleConfig(type="tests", scope="tests")]
    else:
        raise ValueError(f"Unknown scope: {scope}")

    if with_tests and scope != "tests":
        cycles.append(CycleConfig(type="tests", scope="tests", depends_on=[cycles[-1].type]))

    return cycles
```

### Engine State Model

```python
class WorkflowState(BaseModel):
    # Existing fields...
    session_id: str
    profile_name: str
    context: dict[str, Any]

    # v3 additions
    cycles: list[CycleState]
    current_cycle_index: int = 0

class CycleState(BaseModel):
    type: str                    # "domain", "service", "api", "tests"
    scope: str                   # Scope passed to profile methods
    phase: WorkflowPhase         # Current phase within this cycle
    stage: WorkflowStage         # PROMPT or RESPONSE
    status: WorkflowStatus       # IN_PROGRESS, COMPLETED, ERROR
    iterations: list[IterationState]
    current_iteration: int = 1
```

### CLI Changes

**New flag:**

```bash
# Generate code and tests in one session
aiwf init jpa-mt -c scope=domain --with-tests
```

**Status output:**

```
Session: abc123
Cycle: 2/4 (service)
Phase: GENERATE[RESPONSE]
Status: IN_PROGRESS

Cycles:
  [✓] domain (completed)
  [→] service (in progress)
  [ ] api (pending)
  [ ] tests (pending)
```

### Cycle Transitions

After a cycle completes (reaches COMPLETE status):

1. Engine checks if more cycles exist
2. If yes, advance `current_cycle_index`
3. Initialize next cycle at PLAN[PROMPT]
4. Pass previous cycle outputs as context (for `depends_on`)

If a cycle fails (ERROR or user rejects):
- Session can be resumed at failed cycle
- Previous completed cycles remain intact
- User can fix and retry failed cycle

### Context Passing Between Cycles

Each cycle can access outputs from previous cycles via context:

```python
context = {
    "entity": "Product",
    "scope": "service",  # Current cycle's scope
    "cycle_outputs": {
        "domain": {
            "files": ["Product.java", "ProductRepository.java"],
            "artifacts": {...}  # Loaded content if needed
        }
    }
}
```

The `depends_on` field in CycleConfig tells the engine which previous cycles' outputs to load.

---

## Migration from v2.x

### Session Linking Preserved

The `--source-session` and `--source-files` flags from v2.x continue to work:

```bash
# Still valid in v3
aiwf init jpa-mt -c scope=tests --source-session abc123
```

This creates a single-cycle session (`tests` only) that loads external sources. Useful for:
- Generating tests for existing codebase code
- Regenerating tests independently

### Single-Cycle Sessions

v3 is backward compatible. A session with one cycle behaves like v2.x:

```bash
# Creates single-cycle session (domain only)
aiwf init jpa-mt -c scope=domain
```

Directory structure for single-cycle matches v2.x layout under the type directory.

### Upgrade Path

Existing v2.x sessions are not migrated. They remain in v2.x format and can complete normally. v3 sessions use the new structure from initialization.

---

## Implementation Phases

### Phase 1: State Model

1. Add `CycleState` model
2. Extend `WorkflowState` with cycles list
3. Update `SessionStore` for new structure
4. Backward compatibility for v2.x session loading

### Phase 2: Directory Structure

1. Create `<type>/iteration-{N}/` directories
2. Update file path resolution throughout engine
3. Update prompt/response file locations

### Phase 3: Profile Interface

1. Add `get_cycles()` to `WorkflowProfile` ABC
2. Update `jpa-mt` profile implementation
3. Add `CycleConfig` dataclass

### Phase 4: Engine Orchestration

1. Cycle initialization logic
2. Cycle transition after COMPLETE
3. Context passing between cycles
4. Error handling per cycle

### Phase 5: CLI Updates

1. Add `--with-tests` flag
2. Update `status` command for multi-cycle display
3. Update `approve`/`reject` for cycle context

### Phase 6: Scope Decomposition

1. Update `full` scope to use cycles: domain → service → api
2. Test cycle dependencies
3. Validate token budget improvements

---

## Open Questions

1. **Cycle retry granularity** - Can user retry just GENERATE phase of a cycle, or must restart whole cycle?

2. **Parallel cycles** - Should engine support running independent cycles in parallel? (e.g., domain and api don't depend on each other)

3. **Cycle skipping** - Can user skip a cycle? (e.g., `--skip-tests` to run domain → service → api without tests)

4. **Mixed v2/v3 sessions** - If user starts v2.x session then upgrades engine, what happens?

5. **Cycle-specific config** - Should workflow config support per-cycle overrides? (e.g., different AI provider for tests)

---

## Consequences

### Positive

1. **Smaller prompts** - Each cycle has focused context
2. **Independent iteration** - Fix one layer without regenerating others
3. **Integrated tests** - Single command for code + tests
4. **Clear organization** - Output grouped by purpose
5. **Profile control** - Profiles define their own cycle structure

### Negative

1. **Increased complexity** - Engine manages cycles + phases + stages
2. **Longer sessions** - Multi-cycle sessions take more wall time
3. **State model changes** - Breaking change from v2.x state format

### Risks

| Risk | Mitigation |
|------|------------|
| Cycle state corruption | Transaction-like cycle completion, rollback on failure |
| Context bloat between cycles | Lazy loading, only load what depends_on requires |
| User confusion | Clear status output showing cycle progress |

---

## Related Documents

- **ADR-0012**: Phase+Stage Model (foundation for cycle phases)
- **ADR-0018**: Test Generation Scopes (v2.x approach, migrates to v3)
- **ADR-0008**: Engine-Profile Separation (profile provides cycles, engine executes)

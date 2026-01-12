# ADR-0001: Architecture Overview

**Status:** Accepted
**Date:** December 2, 2024
**Last Updated:** December 30, 2024
**Deciders:** Scott

> **Note:** This document supersedes the previous version (commit `051ae1b`). The workflow model was redesigned per ADR-0012, replacing the ING/ED phase model with a Phase+Stage model and TransitionTable state machine.

---

## Context and Problem Statement

We need an AI-assisted development workflow engine that orchestrates multi-phase generation (plan → generate → review → revise), supports interactive/manual workflows as well as automated workflows, persists state, and allows domain-specific "profiles" without modifying core engine logic.

This engine generalizes lessons learned from building real-world AI-assisted development tooling while remaining independent of any proprietary domain logic.

---

## Decision Drivers

1. Architectural clarity and long-term maintainability
2. Extensibility through pluggable profiles
3. Clean, testable boundaries between workflow logic, providers, and templates
4. Ability to support both interactive (manual copy/paste) and automated (API) execution
5. State persistence for resumability and crash recovery
6. Clear contracts for IDE extensions (VS Code, IntelliJ)
7. Full audit trail with iteration tracking
8. Security by design (input validation, path safety)

---

## Decision Outcome

Adopt a layered architecture using Strategy (profiles, providers, standards), Factory, Repository, and State patterns. The workflow uses a Phase+Stage model with a declarative TransitionTable state machine.

**Patterns adopted:** Strategy, Factory, Repository, State (TransitionTable)
**Patterns tried and replaced:** Chain of Responsibility (see ADR-0005, superseded by ADR-0012)

---

## Architecture

```
+---------------------------------------------+
|  Interface Layer (CLI)                      |
+---------------------------------------------+
|  Application Layer (Services)               |
|  - WorkflowOrchestrator, TransitionTable    |
+---------------------------------------------+
|  Domain Layer (Core)                        |
|  - Models, Profiles, Providers              |
+---------------------------------------------+
|  Infrastructure Layer (Adapters)            |
|  - AI Providers, Filesystem, Validation     |
+---------------------------------------------+
```

---

## Core Domain Model

### Phase+Stage Model

The workflow uses 8 phases, with active phases having 2 stages each:

```python
class WorkflowPhase(str, Enum):
    INIT = "init"           # Session initialized
    PLAN = "plan"           # Creating development plan
    GENERATE = "generate"   # Generating code
    REVIEW = "review"       # Reviewing generated code
    REVISE = "revise"       # Revising based on feedback
    COMPLETE = "complete"   # Workflow finished
    ERROR = "error"         # Stopped due to error
    CANCELLED = "cancelled" # Cancelled by user

class WorkflowStage(str, Enum):
    PROMPT = "prompt"       # Working on prompt, awaiting approval
    RESPONSE = "response"   # Working on response, awaiting approval

class WorkflowStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"
```

### Stage Transitions

```
PHASE[PROMPT] ──approve──► PHASE[RESPONSE] ──approve──► NEXT_PHASE[PROMPT]
      │                          │
      └── prompt editable        └── AI called, response editable
```

Work happens AFTER entering each stage:
- Enter PROMPT → profile creates prompt → user can edit → approve
- Enter RESPONSE → AI produces response → user can edit → approve

---

## TransitionTable State Machine

The `TransitionTable` is a declarative state machine that handles all workflow transitions:

```python
class TransitionTable:
    """Declarative state machine for workflow transitions."""

    def get_transition(
        self,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        command: str,  # "approve", "reject", "retry"
    ) -> Transition:
        """Look up the transition for the current state and command."""
        ...
```

Each transition specifies:
- Next phase and stage
- Action to execute (e.g., `CREATE_PROMPT`, `CALL_PROVIDER`, `EXTRACT_CODE`)
- Validation rules

---

## Commands

| Command | Purpose |
|---------|---------|
| `init` | Initialize session, enter PLAN[PROMPT], create planning prompt |
| `approve` | Accept pending content, advance to next stage/phase |
| `reject` | Reject pending content with feedback, halt workflow |
| `retry` | Re-invoke AI provider with feedback to regenerate |
| `status` | Show current workflow state |

**Approve commits. Reject halts. Retry regenerates.**

---

## Workflow Flow

```
init ──► PLAN[PROMPT] (prompt created)
              │
              ▼ approve
         PLAN[RESPONSE] (AI called, plan ready)
              │
              ▼ approve
         GENERATE[PROMPT] (prompt created)
              │
              ▼ approve
         GENERATE[RESPONSE] (AI called, code ready)
              │
              ▼ approve
         REVIEW[PROMPT] (prompt created)
              │
              ▼ approve
         REVIEW[RESPONSE] (AI called, verdict ready)
              │
              ▼ approve (verdict determines next)
         COMPLETE or REVISE[PROMPT]
```

---

## Iteration Semantics

- Iteration 1 is created when entering GENERATE phase
- The iteration number increments only when REVIEW verdict is FAIL → REVISE
- The iteration number remains stable across all other transitions
- No iteration directories are created speculatively

---

## Canonical File Locations

### Session-Scoped Files

```
.aiwf/sessions/{session-id}/
├── session.json             # Workflow state
├── standards-bundle.md      # Created at init, immutable
└── plan.md                  # Created in PLAN phase
```

### Iteration-Scoped Files

```
.aiwf/sessions/{session-id}/
├── iteration-1/
│   ├── plan-prompt.md
│   ├── plan-response.md
│   ├── generate-prompt.md
│   ├── generate-response.md
│   ├── review-prompt.md
│   ├── review-response.md
│   └── code/
│       ├── Entity.java
│       └── EntityRepository.java
│
└── iteration-2/                 # Created only if revision needed
    ├── revise-prompt.md
    ├── revise-response.md
    ├── review-prompt.md
    ├── review-response.md
    └── code/
        └── [revised files]
```

---

## WorkflowState Model

```python
class WorkflowState(BaseModel):
    # Identity
    session_id: str
    profile: str
    scope: str
    entity: str

    # Context
    bounded_context: str | None = None
    table: str | None = None

    # State
    phase: WorkflowPhase
    stage: WorkflowStage | None  # None for INIT, COMPLETE, ERROR, CANCELLED
    status: WorkflowStatus
    current_iteration: int = 1

    # Approval
    approval_feedback: str | None = None  # Feedback from reject/retry

    # Hashing
    standards_hash: str
    plan_hash: str | None = None
    prompt_hashes: dict[str, str] = {}

    # Multi-provider strategy
    providers: dict[str, str]  # role -> provider_key

    # Artifacts
    artifacts: list[Artifact] = []

    # Error tracking
    last_error: str | None = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
```

---

## Repository Structure

```
ai-workflow-engine/
├── aiwf/
│   ├── domain/
│   │   ├── models/              # WorkflowState, Artifact, ProcessingResult
│   │   ├── profiles/            # WorkflowProfile interface + Factory
│   │   ├── providers/           # AIProvider interface + Factory
│   │   ├── persistence/         # SessionStore
│   │   └── validation/          # PathValidator
│   ├── application/
│   │   ├── workflow_orchestrator.py  # Main engine
│   │   ├── transitions.py            # TransitionTable state machine
│   │   ├── approval_handler.py       # run_provider() utility
│   │   └── prompt_assembler.py       # Prompt assembly
│   └── interface/
│       └── cli/                 # CLI commands, output models
├── profiles/
│   └── jpa_mt/                  # JPA multi-tenant profile
├── docs/
│   └── adr/                     # Architecture Decision Records
└── tests/
    ├── unit/
    └── integration/
```

---

## Patterns Adopted

### 1. Strategy Pattern (AI Providers)

**Problem:** Need to swap LLM backends (Claude, Gemini, manual mode) without changing workflow logic.

**Solution:** `AIProvider` abstract base class with concrete implementations.

```python
class AIProvider(ABC):
    def generate(self, prompt: str, **kwargs) -> str | None:
        """Generate response. Returns None for manual mode."""
        ...
```

### 2. Strategy Pattern (Workflow Profiles)

**Problem:** Different code generation domains have different templates, standards, and parsing rules.

**Solution:** `WorkflowProfile` abstract base class with domain-specific implementations.

```python
class WorkflowProfile(ABC):
    def get_standards_provider(self) -> StandardsProvider: ...
    def generate_plan_prompt(self, context: dict) -> str: ...
    def generate_generate_prompt(self, context: dict) -> str: ...
    def process_plan_response(self, content: str) -> ProcessingResult: ...
    def process_generate_response(self, content: str, ...) -> ProcessingResult: ...
```

### 3. Factory Pattern

**Problem:** Need runtime instantiation of providers and profiles based on configuration.

**Solution:** `ProviderFactory` and `ProfileFactory` with registration systems.

### 4. Repository Pattern

**Problem:** Need to abstract persistence mechanism for workflow state.

**Solution:** `SessionStore` encapsulates all file I/O for session state.

### 5. State Pattern (TransitionTable)

**Problem:** Workflow behavior changes based on current phase and stage.

**Solution:** Declarative `TransitionTable` that maps (phase, stage, command) → transition.

---

## Patterns Tried and Replaced

### Chain of Responsibility (ADR-0005)

**Tried:** Approval handling via a chain of handler objects.

**Replaced by:** TransitionTable state machine (ADR-0012).

**Rationale:** The Chain of Responsibility added indirection without enabling new capabilities. The TransitionTable provides clearer, more testable state transitions with less code.

---

## Responsibility Boundaries

### Profiles
- Parse AI responses
- Generate prompt content
- Return WritePlan (what to write)
- **Never read or write files**
- **Never mutate workflow state**

### Engine (WorkflowOrchestrator)
- Owns all session file I/O
- Executes WritePlan
- Computes all hashes
- Advances workflow state via TransitionTable

### Providers
- Accept prompt content
- Return response content (or None for manual mode)

---

## Execution Mode vs Providers

These are orthogonal concerns:

| Concern | Question | Options |
|---------|----------|---------|
| **Execution Mode** | Who drives the workflow? | `INTERACTIVE`, `AUTOMATED` |
| **Providers** | Who produces responses? | `manual`, `claude`, `gemini`, etc. |

Combinations:
- INTERACTIVE + manual: User copies prompts to AI, runs approve
- INTERACTIVE + claude: User controls timing, API produces content
- AUTOMATED + all API: Full automation for CI/CD

---

## Non-Enforcement Policy

This engine is **not adversarial**.

- Editing files is allowed at any time
- Hash mismatches log warnings but **never block workflow**
- Hashes exist for audit trail, not enforcement

---

## Consequences

### Positive

1. **Clear mental model** — Phase+Stage is easier to understand than 10+ discrete phases
2. **Testable** — TransitionTable is pure data, easily tested
3. **Extensible** — New profiles without core changes
4. **Resumable** — Persistent state enables crash recovery
5. **Flexible** — reject/retry commands enable iterative refinement

### Negative

1. **Upfront complexity** — More design work than simple scripts
2. **Learning curve** — Contributors need to understand patterns

---

## Related Decisions

- ADR-0002: Template Layering System
- ADR-0003: Workflow State Validation with Pydantic
- ADR-0004: Structured Review Metadata
- ADR-0007: Plugin Architecture
- ADR-0012: Workflow Phases, Stages, and Approval Providers (defines current model)

---

**Document Status:** Living document
**Last Reviewed:** December 30, 2024
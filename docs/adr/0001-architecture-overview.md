# ADR-0001: Architecture Overview

**Status:** Accepted  
**Date:** December 2, 2024  
**Last Updated:** December 24, 2024  
**Deciders:** Scott

---

## Context and Problem Statement

We need an AI-assisted development workflow engine that orchestrates multi-phase generation (plan -> generate -> review -> revise), supports interactive/manual workflows as well as automated workflows, persists state, and allows domain-specific "profiles" without modifying core engine logic. A prior workflow, built as Python scripts, demonstrated the core flow but lacked architectural structure, extensibility, and clarity.

This engine is designed to generalize the lessons learned from building real-world AI-assisted development tooling while remaining independent of any proprietary domain logic. It must support legacy-style workflows without adopting their internal designs.

---

## Decision Drivers

1. Architectural clarity and long-term maintainability
2. Extensibility through pluggable profiles
3. Clean, testable boundaries between workflow logic, providers, and templates
4. Ability to support both interactive (manual copy/paste) and automated (CLI-provider) execution
5. State persistence to allow resumability and crash recovery
6. Clear contracts for IDE extensions (VS Code, IntelliJ)
7. Full audit trail with iteration tracking
8. Security by design (input validation, path safety)

---

## Considered Options

### Option 1: Continue Script-Based Workflows
**Pros:** Already functional; minimal effort  
**Cons:** No architecture; hard to extend; domain-specific coupling

### Option 2: Monolithic Engine
**Pros:** Simple to implement  
**Cons:** Poor separation of concerns; limited extensibility

### Option 3: Layered Architecture (Chosen)
**Pros:** Clean boundaries; extensible via profiles; demonstrates appropriate design patterns; supports multiple execution modes  
**Cons:** Higher initial design cost

---

## Decision Outcome

Adopt a layered architecture using Strategy (3 uses), Factory, Repository, and procedural State patterns. Introduce profiles that encapsulate workflow-specific templates, standards, and parsing rules. Profiles delegate to StandardsProvider implementations for standards retrieval.

**Patterns adopted:** Strategy, Factory, Repository, State (procedural)  
**Patterns considered and rejected:** Chain of Responsibility, Command, Builder, Adapter, Observer, Decorator

See "Pattern Justifications" section below for detailed rationale.

---

## Architecture

Interface Layer -> Application Layer -> Domain Layer -> Infrastructure Layer

```
+---------------------------------------------+
|  Interface Layer (CLI)                      |
+---------------------------------------------+
|  Application Layer (Services)               |
+---------------------------------------------+
|  Domain Layer (Core)                        |
|  - Models, Patterns, Abstractions           |
+---------------------------------------------+
|  Infrastructure Layer (Adapters)            |
|  - AI Providers, Filesystem, Validation     |
+---------------------------------------------+
```

---

## Core Domain Model

```python
class WorkflowPhase(str, Enum):
    INITIALIZED = "initialized"

    # Planning
    PLANNING = "planning"      # ING: prompt issuance + artifact gate
    PLANNED = "planned"        # ED: gates on plan_approved

    # Generation
    GENERATING = "generating"  # ING: prompt issuance, response processing, code extraction
    GENERATED = "generated"    # ED: gates on artifact hashes

    # Review
    REVIEWING = "reviewing"    # ING: prompt issuance + artifact gate
    REVIEWED = "reviewed"      # ED: gates on review_approved, processes verdict

    # Revision (mirrors generation)
    REVISING = "revising"      # ING: prompt issuance, response processing, code extraction
    REVISED = "revised"        # ED: gates on artifact hashes

    # Terminal
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class WorkflowStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"
```

---

## Phase Responsibility Split

### ING Phases: PLANNING, REVIEWING

Responsible for:
- Issuing the appropriate prompt artifact if missing
- Gating on response artifact presence
- Transitioning to ED phase when response exists

Must not:
- Process response content
- Extract code or artifacts

### ING Phases with Processing: GENERATING, REVISING

Responsible for:
- Issuing the appropriate prompt artifact if missing
- When response exists: process via profile, extract code, write artifacts
- Transitioning to ED phase after processing

Note: This deviates from pure ING/ED separation but maintains correct behavior.

### ED Phases: PLANNED, GENERATED, REVIEWED, REVISED

Responsible for:
- Gating on approval state (approval must occur before advancement)
- PLANNED: gates on `plan_approved == True`
- GENERATED/REVISED: gates on all artifacts having `sha256` set
- REVIEWED: gates on `review_approved == True`, then processes verdict

Must not:
- Create prompt artifacts
- Process responses (except REVIEWED processing verdict after approval)

---

## Approval System

### Core Principle

> Every output must be editable before it becomes input to the next step.

### Commands

| Command | Responsibility |
|---------|----------------|
| `aiwf step {session_id}` | Perform deterministic engine work, advance phases |
| `aiwf approve {session_id}` | Hash artifacts, set approval flags, call providers |

**Step advances. Approve commits.**

### Approval Gates

| Phase | Gate Condition | What Gets Hashed |
|-------|----------------|------------------|
| PLANNED | `plan_approved == True` | `plan.md` -> `plan_hash` |
| GENERATED | All artifacts have `sha256` | `iteration-N/code/*` files |
| REVIEWED | `review_approved == True` | `review-response.md` -> `review_hash` |
| REVISED | All artifacts have `sha256` | `iteration-N/code/*` files |

### Deferred Hashing

Artifacts are written with `sha256=None` during `step()`. Hashes are computed during `approve()` to capture any user edits.

---

## Iteration Semantics

- Iteration 1 is created when entering GENERATING.
- The iteration number increments only when:
  - REVIEWED -> REVISING occurs due to a FAIL outcome.
- The iteration number remains stable across all other phases and transitions.
- No iteration directories are created speculatively or implicitly.

---

## Canonical File Locations

### Session-Scoped Files

```
.aiwf/sessions/{session-id}/
|-- session.json             # Workflow state
|-- standards-bundle.md      # Created at init, immutable
|-- plan.md                  # Created in PLANNED, hashed on approval
```

### Iteration-Scoped Files

```
.aiwf/sessions/{session-id}/
|-- iteration-1/
|   |-- planning-prompt.md
|   |-- planning-response.md
|   |-- generation-prompt.md
|   |-- generation-response.md
|   |-- review-prompt.md
|   |-- review-response.md
|   |-- code/
|       |-- Entity.java
|       |-- EntityRepository.java
|
|-- iteration-2/                 # Created only if revision needed
    |-- revision-prompt.md
    |-- revision-response.md
    |-- review-prompt.md
    |-- review-response.md
    |-- code/
        |-- [revised files]
```

### File Naming Convention

Prompt and response files use the phase name without "-ing" suffix:
- `planning-prompt.md`, `planning-response.md`
- `generation-prompt.md`, `generation-response.md`
- `review-prompt.md`, `review-response.md`
- `revision-prompt.md`, `revision-response.md`

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
    dev: str | None = None
    task_id: str | None = None
    
    # State
    phase: WorkflowPhase
    status: WorkflowStatus
    execution_mode: ExecutionMode
    current_iteration: int = 1
    
    # Hashing and approval
    standards_hash: str
    plan_approved: bool = False
    plan_hash: str | None = None
    prompt_hashes: dict[str, str] = {}
    review_approved: bool = False
    review_hash: str | None = None
    
    # Multi-provider strategy
    providers: dict[str, str]  # role -> provider_key
    
    # Extensibility
    metadata: dict[str, Any] = {}
    
    # Artifacts
    artifacts: list[Artifact] = []
    
    # Interactive mode
    pending_action: str | None = None
    
    # Error tracking
    last_error: str | None = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # History
    phase_history: list[PhaseTransition] = []
```

---

## Repository Structure
```
ai-workflow-engine/
├── aiwf/
│   ├── domain/
│   │   ├── models/              # WorkflowState, Artifact, ProcessingResult, WritePlan
│   │   ├── profiles/            # WorkflowProfile interface + Factory
│   │   ├── providers/           # AIProvider interface + Factory
│   │   ├── persistence/         # SessionStore
│   │   └── validation/          # PathValidator
│   ├── application/             # WorkflowOrchestrator, ConfigLoader, ApprovalHandler
│   ├── infrastructure/          # Provider implementations (planned for v1.0.0)
│   └── interface/
│       └── cli/                 # CLI commands, output models
├── profiles/
│   └── jpa_mt/                  # JPA multi-tenant profile
│       ├── jpa_mt_profile.py
│       ├── jpa_mt_config.py
│       ├── jpa_mt_standards_provider.py
│       ├── bundle_extractor.py
│       ├── review_metadata.py
│       └── templates/
├── docs/
│   └── adr/                     # Architecture Decision Records
└── tests/
    ├── unit/
    └── integration/
```

---

## Pattern Justifications

This section documents design patterns adopted and rejected for v0.9.0.

---

## Patterns Adopted

### 1. Strategy Pattern (AI Providers)

**Problem:** Need to swap LLM backends (Claude CLI, Gemini CLI, manual mode) without changing workflow logic.

**Solution:** `AIProvider` abstract base class with concrete implementations.

**Implementation:**
```python
# aiwf/domain/providers/ai_provider.py
class AIProvider(ABC):
    async def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str: ...
```

**Status:** Interface and factory implemented in v0.9.0. Manual mode (user handles AI interaction externally) is the default. Automated provider implementations planned for v1.0.0.

---

### 2. Strategy Pattern (Workflow Profiles)

**Problem:** Different code generation domains have different templates, standards, and parsing rules.

**Solution:** `WorkflowProfile` abstract base class with domain-specific implementations.

**Implementation:**
```python
# aiwf/domain/profiles/workflow_profile.py
class WorkflowProfile(ABC):
    def get_standards_provider(self) -> StandardsProvider: ...
    def generate_planning_prompt(self, context: dict) -> str: ...
    def generate_generation_prompt(self, context: dict) -> str: ...
    def generate_review_prompt(self, context: dict) -> str: ...
    def generate_revision_prompt(self, context: dict) -> str: ...
    def process_planning_response(self, content: str) -> ProcessingResult: ...
    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult: ...
    def process_review_response(self, content: str) -> ProcessingResult: ...
    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult: ...

# profiles/jpa_mt/jpa_mt_profile.py
class JpaMtProfile(WorkflowProfile):
    # Concrete implementation for JPA/Spring Data
```

**Note:** `validate_metadata(metadata: dict[str, Any] | None) -> None` is provided with a default no-op implementation. Profiles override this to enforce required metadata fields.

**Status:** Implemented in v0.9.0

---

### 3. Strategy Pattern (Standards Providers)

**Problem:** Different profiles need different standards retrieval strategies (file-based, RAG, API, Git).

**Solution:** `StandardsProvider` Protocol interface allowing profiles to implement their own standards logic.

**Implementation:**
```python
# aiwf/application/standards_provider.py
class StandardsProvider(Protocol):
    def create_bundle(self, context: dict[str, Any]) -> str: ...

# profiles/jpa_mt/jpa_mt_standards_provider.py
class JpaMtStandardsProvider:
    def create_bundle(self, context: dict[str, Any]) -> str:
        # File-based implementation with scope-aware layer selection
```

**Status:** Implemented in v0.9.0

**Note:** Strategy pattern is used consistently across three architectural concerns (providers, profiles, standards), demonstrating understanding of when and how to apply it appropriately.

---

### 4. Factory Pattern

**Problem:** Need runtime instantiation of providers and profiles based on configuration keys.

**Solution:** `ProviderFactory` and `ProfileFactory` with registration systems.

**Implementation:**
```python
# aiwf/domain/profiles/profile_factory.py
class ProfileFactory:
    _registry: dict[str, type[WorkflowProfile]] = {}
    
    @classmethod
    def register(cls, key: str, profile_class: type[WorkflowProfile]) -> None: ...
    
    @classmethod
    def create(cls, profile_key: str, config: dict[str, Any] | None = None) -> WorkflowProfile: ...
    
    @classmethod
    def list_profiles(cls) -> list[str]: ...

# aiwf/domain/providers/provider_factory.py
class ProviderFactory:
    _registry: dict[str, type[AIProvider]] = {}
    
    @classmethod
    def register(cls, key: str, provider_class: type[AIProvider]) -> None: ...
    
    @classmethod
    def create(cls, provider_key: str, config: dict[str, Any] | None = None) -> AIProvider: ...
    
    @classmethod
    def list_providers(cls) -> list[str]: ...
```

**Status:** Implemented in v0.9.0

---

### 5. Repository Pattern

**Problem:** Need to abstract persistence mechanism for workflow state.

**Solution:** `SessionStore` encapsulates all file I/O for session state.

**Implementation:**
```python
# aiwf/domain/persistence/session_store.py
class SessionStore:
    def save(self, state: WorkflowState) -> Path: ...
    def load(self, session_id: str) -> WorkflowState: ...
    def exists(self, session_id: str) -> bool: ...
    def list_sessions(self) -> list[str]: ...
    def delete(self, session_id: str) -> None: ...
```

**Status:** Implemented in v0.9.0

**Benefits:**
- Application layer never touches filesystem directly
- Easy to swap implementations (JSON files -> database)
- Testable via mock implementations

---

### 6. State Pattern (Procedural Implementation)

**Problem:** Workflow behavior changes based on current phase.

**Solution:** Enum-based state with phase-specific handler methods rather than separate state classes.

**Implementation:**
```python
# aiwf/domain/models/workflow_state.py
class WorkflowPhase(str, Enum):
    INITIALIZED = "initialized"
    PLANNING = "planning"
    PLANNED = "planned"
    # ... etc

# aiwf/application/workflow_orchestrator.py
class WorkflowOrchestrator:
    def step(self, session_id: str) -> WorkflowState:
        state = self.session_store.load(session_id)
        if state.phase == WorkflowPhase.PLANNING:
            return self._step_planning(session_id=session_id, state=state)
        if state.phase == WorkflowPhase.PLANNED:
            return self._step_planned(session_id=session_id, state=state)
        # ... etc
```

**Status:** Implemented in v0.9.0

**Rationale:** Procedural approach with enum and dispatch methods is simpler than full State pattern with separate state classes. Achieves the same behavioral goals without additional complexity.

---

## Patterns Considered and Rejected

### Chain of Responsibility Pattern

**Consideration:** Implement phase transitions and approval handling as a chain of handler objects.

**Decision:** Rejected for v0.9.0

**Rationale:** Chain of Responsibility provides value when: (1) multiple handlers might process a request, (2) the handler set changes dynamically, or (3) the sender shouldn't know which handler processes the request. None of these conditions apply here. Approval logic follows a fixed, linear path determined by workflow phase. The phase is known, the handler is known, and there's no dynamic handler selection. Introducing chain infrastructure would add indirection without enabling any new capability.

**Reconsideration trigger:** If approval expands to include pluggable validators (security checks, test validation, custom rules), Chain of Responsibility would allow dynamic handler composition.

---

### Command Pattern

**Consideration:** Encapsulate operations (approve, step) as Command objects with execute methods.

**Decision:** Rejected

**Rationale:** Command pattern provides value when operations need to be: queued, logged for undo/redo, executed remotely, or composed into macros. This workflow engine has none of these requirements. Operations execute immediately and synchronously. Python's first-class functions already provide the encapsulation benefits that Command offers in languages like Java. Adding Command objects would introduce a layer of indirection that solves no actual problem.

---

### Builder Pattern

**Consideration:** Use fluent Builder for constructing `WorkflowState` or handler chains.

**Decision:** Rejected

**Rationale:** Builder pattern provides value when object construction is complex: many parameters, conditional assembly, or multi-step initialization that must occur in a specific order. `WorkflowState` construction is straightforward—all fields are known upfront and passed directly. Pydantic already provides validation during construction. Python's keyword arguments make construction calls self-documenting. A Builder would add ceremony without improving correctness or readability.

---

### Adapter Pattern

**Consideration:** Create adapters for external tools and services.

**Decision:** Not needed in v0.9.0

**Rationale:** Adapter pattern solves interface incompatibility—it allows a class with one interface to work with code expecting a different interface. This engine has no incompatible interfaces to bridge. `AIProvider` and `StandardsProvider` are designed from scratch as extension points; implementations conform to these interfaces directly rather than adapting pre-existing incompatible code.

**Reconsideration trigger:** If integrating legacy scripts or third-party tools with incompatible interfaces, Adapter would provide clean integration without modifying the external code.

---

### Observer Pattern

**Consideration:** Event notification system for workflow state changes.

**Decision:** Deferred to v1.0.0

**Rationale:** Observer pattern provides value when multiple components need to react to state changes without tight coupling. The current engine operates in manual mode with a single CLI consumer—there are no other observers that need notification. Adding event infrastructure now would be speculative complexity with no current subscriber.

**Reconsideration trigger:** IDE extension integration (VS Code, IntelliJ) would benefit from workflow events for UI updates, progress indicators, and error notifications.

---

### Decorator Pattern

**Consideration:** Add cross-cutting concerns (logging, timing, metrics) via structural decorators that wrap objects.

**Decision:** Not needed in v0.9.0

**Rationale:** The Decorator design pattern (object wrapping for behavior extension) provides value when behavior must be added dynamically at runtime or composed in varying combinations. Current cross-cutting needs are minimal and static. When logging or metrics are needed, Python's native `@decorator` syntax on functions/methods is sufficient and more idiomatic than structural object wrapping.

**Reconsideration trigger:** If multiple optional behaviors need to be composed dynamically (e.g., some sessions need audit logging, others need metrics, others need both), structural Decorator would allow runtime composition.

---

## Repository Structure

```
ai-workflow-engine/
->->-> aiwf/
->   ->->-> domain/
->   ->   ->->-> models/              # WorkflowState, Artifact, ProcessingResult, WritePlan
->   ->   ->->-> profiles/            # WorkflowProfile interface + Factory
->   ->   ->->-> providers/           # AIProvider interface + Factory
->   ->   ->->-> persistence/         # SessionStore
->   ->   ->->-> validation/          # PathValidator
->   ->->-> application/             # WorkflowOrchestrator, ConfigLoader
->   ->->-> infrastructure/          # Provider implementations
->   ->->-> interface/
->       ->->-> cli/                 # CLI commands, output models
->->-> profiles/
->   ->->-> jpa_mt/                  # JPA multi-tenant profile
->       ->->-> config.yml
->       ->->-> jpa_mt_profile.py
->       ->->-> bundle_extractor.py
->       ->->-> file_writer.py
->       ->->-> templates/
->->-> docs/
->   ->->-> adr/                     # Architecture Decision Records
->->-> tests/
    ->->-> unit/
    ->->-> integration/
```

---

## CLI Commands
```bash
# Initialize a new workflow session
aiwf init --scope domain --entity Product --table app.products --bounded-context catalog --schema-file schema.sql

# Advance workflow by one step
aiwf step {session_id}

# Approve current phase (hash artifacts, call providers)
aiwf approve {session_id}
aiwf approve {session_id} --hash-prompts
aiwf approve {session_id} --no-hash-prompts

# Check session status
aiwf status {session_id}
```

**Additional init options:**
- `--dev <name>` — Developer identifier
- `--task-id <id>` — External task/ticket reference

---

## Configuration

### Location Precedence (highest wins)

1. CLI flags
2. `./.aiwf/config.yml` (project-specific)
3. `~/.aiwf/config.yml` (user-specific)
4. Built-in defaults

### Structure
```yaml
profile: jpa-mt

providers:
  planner: manual
  generator: manual
  reviewer: manual
  reviser: manual

hash_prompts: false

dev: null
```

**Note on `manual` provider:** Setting a role to `manual` means no programmatic AI invocation occurs. The user obtains AI responses externally (copy/paste to AI chat, or direct an AI agent to process the prompt file) and saves the response file. Automated providers receive prompt content as a string, return response content as a string, and the engine handles all file I/O.

---

## Responsibility Boundaries

### Profiles
- Parse AI responses
- Decide domain-specific policy
- Generate content strings
- Return WritePlan (what to write)
- **Never read or write files**
- **Never mutate workflow state**

### Engine (WorkflowOrchestrator)
- Owns all session file I/O
- Writes all files and artifacts (with `sha256=None`)
- Executes WritePlan
- Computes all hashes (during `approve()`)
- Records approvals
- Advances workflow state

### Providers
- Accept prompt content
- Return response content (AI providers)
- Or no-op (manual provider)

---

## Execution Mode vs Providers (Orthogonal Concerns)

The engine separates two independent concerns that are often conflated:

| Concern | Question | Options |
|---------|----------|---------|
| **Execution Mode** | Who drives the workflow? | `INTERACTIVE`, `AUTOMATED` |
| **Providers** | Who produces responses? | `manual`, `claude`, `gemini`, etc. |

### Execution Mode (Control Flow)

- **INTERACTIVE**: User must issue `step` and `approve` commands to advance the workflow state machine
- **AUTOMATED**: Engine advances automatically without user commands (future: CI/CD pipelines)

### Providers (Data Flow)

- **manual**: No programmatic response; expects response file written externally (by user copy/paste or AI agent)
- **claude/gemini/etc.**: API call produces the response automatically

### Why They Are Orthogonal

These concerns are independent and can be combined in any configuration:

| Mode | Providers | Description |
|------|-----------|-------------|
| INTERACTIVE + all manual | User copies prompts to AI chat, pastes responses, runs step/approve | Budget-friendly, full control |
| INTERACTIVE + claude | User controls *when* (step/approve), Claude produces *what* | Human-paced with API automation |
| AUTOMATED + all non-manual | Full automation end-to-end | CI/CD pipelines, batch processing |
| INTERACTIVE + mixed | Some phases automated, others manual | Automate review, manual generation |

### Key Insight

- "Manual provider" ≠ "Interactive mode" (common source of confusion)
- The CLI flag `--execution-mode interactive` controls who advances the state machine
- Provider configuration controls who produces responses per phase
- These can be configured independently for maximum flexibility

---

## Provider Extension Model

Providers are string-in, string-out. The engine owns all file I/O: it writes prompt files, reads prompt content, calls the provider, and writes response files.

**Manual mode (v0.9.0 default):**
- No provider invocation
- User obtains AI responses externally and saves response files
- Configured via `providers: { role: manual }`

**Automated providers (planned for v1.0.0):**
- Receive prompt content as string, return response content as string
- First-party providers in `aiwf/infrastructure/ai/`
- Implement `AIProvider` interface

**Third-party providers:**
- Distributed as separate packages (e.g., `aiwf-provider-ollama`)
- Register via `ProviderFactory.register()` at import time
- Not part of this repository

**Registration example:**
```python
# In third-party package's __init__.py
from aiwf.domain.providers.provider_factory import ProviderFactory
from ollama_provider import OllamaProvider

ProviderFactory.register("ollama", OllamaProvider)
```

---

## Non-Enforcement Policy

This engine is **not adversarial**.

- Editing files is allowed at any time
- The engine does not refuse to proceed due to file edits
- Hash mismatches log warnings but **never block workflow**

Hashes exist for:
- Audit trail (record what was approved)
- No-op revision detection (UX improvement)
- Post-hoc visibility (debugging)

---

## Consequences

### Positive

1. **Extensible** -> New profiles without core changes
2. **Testable** -> Each layer independently testable
3. **Maintainable** -> Clear separation of concerns
4. **Resumable** -> Persistent state enables crash recovery
5. **Future-proof** -> Architecture supports CLI agents and APIs
6. **Collaborative** -> Clear contracts for IDE extension developers
7. **Language-agnostic** -> Core engine supports any target language through profiles
8. **Secure by design** -> Shared validation prevents common vulnerabilities
9. **Auditable** -> Full iteration tracking with all prompts and responses

### Negative

1. **Upfront complexity** -> More design work than simple scripts
2. **Learning curve** -> New contributors need to understand patterns
3. **Abstraction overhead** -> More files/classes than direct implementation

---

## Related Decisions

- ADR-0002: Template Layering System
- ADR-0003: Workflow State Validation with Pydantic
- ADR-0004: Structured Review Metadata

---

**Document Status:** Living document, updated as implementation progresses  
**Last Reviewed:** December 24, 2024
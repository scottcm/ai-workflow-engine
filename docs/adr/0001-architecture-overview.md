# ADR-0001: Architecture Overview

**Status:** Accepted  
**Date:** December 2, 2024  
**Last Updated:** December 22, 2024  
**Deciders:** Scott

---

## Context and Problem Statement

We need an AI-assisted development workflow engine that orchestrates multi-phase generation (plan → generate → review → revise), supports interactive/manual workflows as well as automated workflows, persists state, and allows domain-specific "profiles" without modifying core engine logic. A prior workflow, built as Python scripts, demonstrated the core flow but lacked architectural structure, extensibility, and clarity.

This engine is designed to generalize the lessons learned from building real-world AI-assisted development tooling while remaining independent of any proprietary domain logic. It must support legacy-style workflows without adopting their internal designs.

---

## Decision Drivers

1. Architectural clarity and long-term maintainability
2. Extensibility through pluggable profiles
3. Clean, testable boundaries between workflow logic, providers, and templates
4. Ability to support both interactive (manual copy/paste) and automated (CLI-provider) execution
5. State persistence to allow resumability and crash recovery
6. Clear contracts for a VS Code extension
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

Adopt a layered architecture using Strategy, Factory, Chain of Responsibility, Command, Builder, Adapter, and Template Method patterns. Introduce profiles that encapsulate workflow-specific templates, standards, and parsing rules.

---

## Architecture

Interface Layer → Application Layer → Domain Layer → Infrastructure Layer

```
┌─────────────────────────────────────────┐
│  Interface Layer (CLI)                  │
├─────────────────────────────────────────┤
│  Application Layer (Services)           │
├─────────────────────────────────────────┤
│  Domain Layer (Core)                    │
│  - Models, Patterns, Abstractions       │
├─────────────────────────────────────────┤
│  Infrastructure Layer (Adapters)        │
│  - AI Providers, Filesystem, Validation │
└─────────────────────────────────────────┘
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
| PLANNED | `plan_approved == True` | `plan.md` → `plan_hash` |
| GENERATED | All artifacts have `sha256` | `iteration-N/code/*` files |
| REVIEWED | `review_approved == True` | `review-response.md` → `review_hash` |
| REVISED | All artifacts have `sha256` | `iteration-N/code/*` files |

### Deferred Hashing

Artifacts are written with `sha256=None` during `step()`. Hashes are computed during `approve()` to capture any user edits.

---

## Iteration Semantics

- Iteration 1 is created when entering GENERATING.
- The iteration number increments only when:
  - REVIEWED → REVISING occurs due to a FAIL outcome.
- The iteration number remains stable across all other phases and transitions.
- No iteration directories are created speculatively or implicitly.

---

## Canonical File Locations

### Session-Scoped Files

```
.aiwf/sessions/{session-id}/
├── session.json             # Workflow state
├── standards-bundle.md      # Created at init, immutable
└── plans/
    └── plan.md              # Created in PLANNED, hashed on approval
```

### Iteration-Scoped Files

```
.aiwf/sessions/{session-id}/
├── prompts/
│   └── planning-prompt.md
├── responses/
│   └── planning-response.md
├── iteration-1/
│   ├── prompts/
│   │   ├── generation-prompt.md
│   │   └── review-prompt.md
│   ├── responses/
│   │   ├── generation-response.md
│   │   └── review-response.md
│   └── code/
│       ├── Entity.java
│       └── EntityRepository.java
│
└── iteration-2/              # Created only if revision needed
    ├── prompts/
    │   ├── revision-prompt.md
    │   └── review-prompt.md
    ├── responses/
    │   ├── revision-response.md
    │   └── review-response.md
    └── code/
        └── [revised files]
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
    bounded_context: str | None
    table: str | None
    dev: str | None
    task_id: str | None
    providers: dict[str, str]  # role -> provider_key
    execution_mode: ExecutionMode
    metadata: dict[str, Any]
    
    # State
    phase: WorkflowPhase
    status: WorkflowStatus
    current_iteration: int = 1
    
    # Hashing and approval
    standards_hash: str
    plan_approved: bool = False
    plan_hash: str | None = None
    review_approved: bool = False
    review_hash: str | None = None
    prompt_hashes: dict[str, str] = {}
    
    # Artifacts
    artifacts: list[Artifact] = []
    
    # Error tracking
    last_error: str | None = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # History
    phase_history: list[PhaseTransition] = []
```

---

## Pattern Justifications

### 1. Strategy Pattern (AI Providers)

**Problem:** Need to swap LLM backends (Claude CLI, Gemini CLI, ChatGPT, manual mode) without changing workflow logic.

**Solution:** `AIProvider` interface with concrete implementations.

```python
class AIProvider(ABC):
    async def generate(self, prompt: str, context: dict | None) -> str: ...
```

### 2. Strategy Pattern (Workflow Profiles)

**Problem:** Different code generation domains have different templates, standards, and parsing rules.

**Solution:** `WorkflowProfile` interface where profiles are concrete implementations.

```python
class WorkflowProfile(ABC):
    def generate_planning_prompt(self, context: dict) -> str: ...
    def generate_generation_prompt(self, context: dict) -> str: ...
    def generate_review_prompt(self, context: dict) -> str: ...
    def generate_revision_prompt(self, context: dict) -> str: ...
    def process_planning_response(self, content: str) -> ProcessingResult: ...
    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult: ...
    def process_review_response(self, content: str) -> ProcessingResult: ...
    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult: ...
```

### 3. Factory Pattern

**Problem:** Need runtime instantiation of providers and profiles based on configuration.

**Solution:** `ProviderFactory` and `ProfileFactory` with registries.

```python
class ProfileFactory:
    _registry: dict[str, type[WorkflowProfile]] = {}
    
    @classmethod
    def create(cls, profile_key: str, config: dict | None = None) -> WorkflowProfile: ...
    
    @classmethod
    def register(cls, key: str, profile_class: type[WorkflowProfile]): ...
```

### 4. Chain of Responsibility Pattern

**Problem:** Workflow phases need conditional execution based on state.

**Solution:** Handler chain where each handler decides whether to process or pass to next.

### 5. Command Pattern

**Problem:** Operations need encapsulation for testability.

**Solution:** Each operation is a command with execute methods.

### 6. Builder Pattern

**Problem:** Handler chains are complex to construct.

**Solution:** Fluent `WorkflowBuilder` that constructs valid chains.

### 7. Adapter Pattern

**Problem:** Need to integrate external tools without tight coupling.

**Solution:** Adapters wrap external dependencies.

### 8. Template Method Pattern

**Problem:** Prompts follow a common structure but vary by profile.

**Solution:** `PromptTemplate` base class with overridable sections.

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
│   ├── application/             # WorkflowOrchestrator, ConfigLoader
│   ├── infrastructure/          # Provider implementations
│   └── interface/
│       └── cli/                 # CLI commands, output models
├── profiles/
│   └── jpa_mt/                  # JPA multi-tenant profile
│       ├── config.yml
│       ├── jpa_mt_profile.py
│       ├── bundle_extractor.py
│       ├── file_writer.py
│       └── templates/
├── docs/
│   └── adr/                     # Architecture Decision Records
└── tests/
    ├── unit/
    └── integration/
```

---

## CLI Commands

```bash
# Initialize a new workflow session
aiwf init --scope domain --entity Product --table app.products --bounded-context catalog

# Advance workflow by one step
aiwf step {session_id}

# Approve current phase (hash artifacts, call providers)
aiwf approve {session_id}
aiwf approve {session_id} --hash-prompts
aiwf approve {session_id} --no-hash-prompts

# Check session status
aiwf status {session_id}
```

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

1. **Extensible** — New profiles without core changes
2. **Testable** — Each layer independently testable
3. **Maintainable** — Clear separation of concerns
4. **Resumable** — Persistent state enables crash recovery
5. **Future-proof** — Architecture supports CLI agents and APIs
6. **Collaborative** — Clear contracts for VS Code extension developer
7. **Language-agnostic** — Core engine supports any target language through profiles
8. **Secure by design** — Shared validation prevents common vulnerabilities
9. **Auditable** — Full iteration tracking with all prompts and responses

### Negative

1. **Upfront complexity** — More design work than simple scripts
2. **Learning curve** — New contributors need to understand patterns
3. **Abstraction overhead** — More files/classes than direct implementation

---

## Related Decisions

- ADR-0002: Template Layering System
- ADR-0003: Workflow State Validation with Pydantic
- ADR-0004: Structured Review Metadata

---

**Document Status:** Living document, updated as implementation progresses  
**Last Reviewed:** December 22, 2024
# ADR-0001: Architecture Overview

**Status:** Accepted  
**Date:** December 2, 2024  
**Last Updated:** December 6, 2024  
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
    PLANNING = "planning"      # *ING: prompt issuance + artifact gate
    PLANNED = "planned"        # *ED: process planning response

    # Generation
    GENERATING = "generating"  # *ING: prompt issuance + artifact gate
    GENERATED = "generated"    # *ED: process generation response + extract code

    # Review
    REVIEWING = "reviewing"    # *ING: prompt issuance + artifact gate
    REVIEWED = "reviewed"      # *ED: process review response

    # Revision (mirrors generation)
    REVISING = "revising"      # *ING: prompt issuance + artifact gate
    REVISED = "revised"        # *ED: process revision response + extract code

    # Terminal
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"
```

---

## Phase Responsibility Split

This ADR is amended to clarify phase responsibilities as implemented and enforced by tests.

### `*ING` phases
(`PLANNING`, `GENERATING`, `REVIEWING`, `REVISING`)

Responsible only for:
- issuing the appropriate prompt artifact if missing
- gating on artifact presence

Must not:
- process response artifacts
- advance phase when required artifacts are missing

If the required response artifact is missing, `step()` returns state unchanged.

### `*ED` phases
(`PLANNED`, `GENERATED`, `REVIEWED`, `REVISED`)

Responsible only for:
- processing the corresponding response artifact via the profile
- extracting/materializing code where applicable
- setting workflow phase and status
- persisting state and appending phase history

Must not:
- create prompt artifacts

If the required response artifact is missing, `step()` returns state unchanged.

---

## Iteration Semantics

This ADR is amended to record iteration behavior enforced by tests.

- Iteration 1 is created when entering `GENERATING`.
- The iteration number increments only when:
  - `REVIEWED → REVISING` occurs due to a FAIL outcome.
- The iteration number remains stable across all other phases and transitions.
- No iteration directories are created speculatively or implicitly.

---

## Revision Symmetry Clarification

Revision mirrors generation structurally.

- `REVISING` behaves like `GENERATING` (prompt issuance + gating).
- `REVISED` behaves like `GENERATED` (response processing + code extraction).
- Revision is not a special case; it follows the same orchestration contract.

---

## Pattern Justifications

Each pattern solves a specific architectural problem:

### 1. Strategy Pattern (AI Providers)

**Problem:** Need to swap LLM backends (Claude CLI, Gemini CLI, ChatGPT, manual mode) without changing workflow logic.

**Solution:** `AIProvider` interface with concrete implementations.

```python
class AIProvider(ABC):
    async def generate(self, prompt: str, context: dict | None) -> str: ...

# Implementations (only ManualProvider is built by this project):
# - ClaudeCliProvider (calls 'claude' CLI)
# - GeminiCliProvider (calls 'gemini' CLI)
# - OllamaGptOssProvider (calls private 'Ollama" using gpt-oss model)
# - ManualProvider (writes prompt to disk, returns placeholder)
```

### 2. Strategy Pattern (Workflow Profiles)

**Problem:** Different code generation domains (ORM, testing, infrastructure) have different templates, standards, and parsing rules.

**Solution:** `WorkflowProfile` interface where profiles are concrete implementations.

```python
class WorkflowProfile(ABC):
    def prompt_template_for(self, phase: WorkflowPhase, scope: str) -> Path: ...
    def standards_bundle_for(self, context: dict) -> str: ...
    def parse_bundle(self, content: str) -> dict[str, str]: ...
    def artifact_dir_for(self, entity: str, scope: str) -> Path: ...
```

### 3. Factory Pattern

**Problem:** Need runtime instantiation of providers and profiles based on configuration.

**Solution:** `ProviderFactory` and `ProfileFactory` with registries.
These are examples of how **custom providers** that wrap agents or make direct API calls could be added.
The current engine only provides "manual".
```python
class ProviderFactory:
    _registry: dict[str, type[AIProvider]] = {
        "claude": ClaudeCliProvider,
        "gemini": GeminiCliProvider,
        "gpt-oss": OllamaGptOssProvider,
        "manual": ManualProvider,
    }
    
    @classmethod
    def create(cls, provider_key: str, config: dict) -> AIProvider: ...
    
    @classmethod
    def register(cls, key: str, provider_class: type[AIProvider]): ...
```

### 4. Chain of Responsibility Pattern

**Problem:** Workflow phases (planning, generation, review, revision) need conditional execution based on state, with different chains per profile.

**Solution:** Handler chain where each handler decides whether to process or pass to next.

```python
class WorkflowHandler(ABC):
    def set_next(self, handler: "WorkflowHandler") -> "WorkflowHandler": ...
    async def handle(self, state: WorkflowState) -> WorkflowState: ...

# Handlers:
# - PlanningHandler
# - GenerationHandler
# - ReviewHandler  
# - RevisionLoopHandler
```

### 5. Command Pattern

**Problem:** Operations need encapsulation for undo capability, logging, and testability.

**Solution:** Each operation is a command with execute/undo methods.

```python
class Command(ABC):
    async def execute(self, state: WorkflowState) -> None: ...
    async def undo(self, state: WorkflowState) -> None: ...

# Commands:
# - PrepareRequestCommand
# - ExtractBundleCommand
# - BuildReviewRequestCommand
# - BuildRevisionRequestCommand
```

### 6. Builder Pattern

**Problem:** Handler chains are complex to construct—easy to forget a handler or wire them incorrectly.

**Solution:** Fluent `WorkflowBuilder` that constructs valid chains.

```python
chain = (WorkflowBuilder(profile, providers, mode)
    .with_planning()
    .with_generation()
    .with_review()
    .with_revision_loop(max_iterations=2)
    .build())
```

### 7. Adapter Pattern

**Problem:** Need to integrate existing scripts and external tools (CLI agents) without tight coupling.

**Solution:** Adapters wrap external dependencies.

```python
# Legacy adapter: wraps existing script logic
class ExtractBundleAdapter:
    def extract(self, bundle_content: str) -> dict[str, str]:
        # Reuses logic from legacy workflow scripts
        return extract_files_from_bundle(bundle_content)

# Provider adapter: wraps Claude CLI
class ClaudeCliProvider(AIProvider):
    async def generate(self, prompt: str, context: dict | None) -> str:
        # Calls 'claude' CLI via subprocess
```

### 8. Template Method Pattern

**Problem:** Prompts follow a common structure (header, metadata, instructions, standards, context) but vary by profile.

**Solution:** `PromptTemplate` base class with overridable sections.

```python
class PromptTemplate(ABC):
    def render(self, context: dict) -> str:
        """Template method - defines skeleton"""
        sections = [
            self._render_header(context),
            self._render_metadata(context),
            self._render_instructions(context),
            self._render_standards(context),
            self._render_context(context),
        ]
        return "\n\n---\n\n".join(s for s in sections if s)
    
    @abstractmethod
    def _render_header(self, context: dict) -> str: ...
    
    @abstractmethod  
    def _render_instructions(self, context: dict) -> str: ...
```

---

## Repository Structure

```
ai-workflow-engine/
├── aiwf/
│   ├── domain/
│   │   ├── models/              # Domain models (WorkflowState, Artifact, etc.)
│   │   ├── profiles/            # Strategy: WorkflowProfile interface + implementations
│   │   ├── providers/           # Strategy: AIProvider interface + Factory
│   │   ├── commands/            # Command: Operation encapsulation
│   │   ├── handlers/            # Chain of Responsibility: Phase handlers
│   │   ├── templates/           # Template Method: Prompt templates
│   │   ├── validation/          # Security utilities (PathValidator)
│   │   ├── persistence/         # SessionStore
│   │   └── workflow/
│   │       ├── builder.py       # Builder: Handler chain construction
│   │       └── executor.py      # Workflow execution with state persistence
│   ├── infrastructure/          # Adapter: External integrations
│   │   ├── ai/                  # AI provider adapters (CLI tools)
│   │   ├── filesystem/          # File operations
│   │   └── legacy/              # Existing script adapters
│   ├── application/             # Application layer
│   │   ├── engine_service.py   # Orchestration
│   │   └── config_service.py   # Configuration loading
│   └── interface/               # Interface layer
│       └── cli/                 # CLI commands
├── profiles/
│   └── jpa-mt/                  # First profile implementation
│       ├── config.yml           # Profile configuration
│       ├── profile.py           # Profile implementation
│       ├── templates/           # Prompt templates
│       │   ├── planning/
│       │   ├── generation/
│       │   ├── review/
│       │   └── revision/
│       └── README.md            # Profile documentation
├── docs/
│   └── adr/                     # Architecture Decision Records
└── tests/
    ├── unit/
    └── integration/
```

---

## Key Architectural Decisions

### 1. Dual Execution Modes (First-Class)

The system explicitly supports two modes:

**Interactive Mode:** For budget-constrained teams using web UIs
- Generates prompt files to disk
- Sets `pending_action` checkpoint in state
- User manually copies/pastes
- Resumes from saved state

**Automated Mode:** For teams with CLI agents or API access
- Directly calls AI providers
- Runs entire workflow without manual intervention
- Still persists state for crash recovery

**Trade-off:** More complexity in handlers (mode-aware behavior) vs. better user experience and future-proofing.

### 2. Profiles Over Configuration

Profiles are **strategies**, not just config files. They encapsulate:
- Scope definitions (domain, vertical, etc.)
- Layer-to-standards mapping
- Template selection logic
- Bundle parsing rules
- Artifact layout conventions
- Standards management approach

**Trade-off:** More code per profile vs. proper separation of domain-specific concerns.

### 3. Scope and Layer Design

**Scope** = What to generate (business request)
- `domain` — Entity + Repository
- `vertical` — Full stack (Entity → Controller)
- `service-only` — Service layer only

**Layer** = Architectural component
- `entity`, `repository`, `service`, `controller`, `dto`, `mapper`

**Configuration:**
```yaml
scopes:
  domain:
    layers: [entity, repository]
  vertical:
    layers: [entity, repository, service, controller, dto, mapper]

layer_standards:
  _universal:
    - PACKAGES_AND_LAYERS.md
  entity:
    - ORG.md
    - JPA_AND_DATABASE.md
    - ARCHITECTURE_AND_MULTITENANCY.md
    - NAMING_AND_API.md
```

**Benefits:**
- Flexible scope definitions without duplicating standards
- Layer-based standards deduplication
- Easy to add custom scopes

### 4. Artifact Directory Structure

**Session Directory** (iteration-based organization):
```
.aiwf/sessions/{session-id}/
├── session.json
├── workflow.log
├── standards-bundle.md          # Immutable
│
├── iteration-1/
│   ├── planning-prompt.md
│   ├── planning-response.md
│   ├── generation-prompt.md
│   ├── generation-response.md
│   ├── review-prompt.md
│   ├── review-response.md
│   └── code/
│
└── iteration-2/                 # Revision
    └── [same structure]
```

**Target Directory** (optional):
```
{target_root}/{entity}/{scope}/
├── standards-bundle.md
├── Entity.java                  # Final code at root
├── EntityRepository.java
├── iteration-1/
└── iteration-2/
```

**Rationale:**
- Iteration folders keep all related artifacts together
- Final code at root level (not in subdirectory) for easy access
- Full audit trail preserved
- Easy to compare iterations

### 5. Standards Bundling Strategy

**Decision:** Session-scoped, immutable standards bundles.

**Approach:**
1. Collect all layers for requested scope
2. Gather standards files for each layer
3. Add universal standards
4. Deduplicate (files referenced multiple times loaded once)
5. Concatenate with separators: `--- FILENAME.md ---`

**Immutability Enforcement:**
- Standards bundled once at session start
- Engine validates bundle hasn't changed between iterations
- Prevents workflow corruption from mid-session standards changes
- If standards update needed, create new session

**Trade-off:** Cannot change standards mid-workflow vs. workflow integrity.

### 6. Security Validation

**Shared Validation Library:** `aiwf/domain/validation/path_validator.py`

**Protections:**
- Entity name sanitization (alphanumeric, hyphens, underscores only)
- Path traversal prevention
- Environment variable expansion safety
- Template variable validation
- Standards file validation (must be within standards root)

**Usage:**
```python
from aiwf.domain.validation import PathValidator

# Sanitize entity name
clean = PathValidator.sanitize_entity_name(entity)

# Validate standards root
root = PathValidator.validate_directory(standards_root)

# Validate standards file
file = validate_standards_file(filename, standards_root)
```

**Trade-off:** More validation overhead vs. security and error prevention.

### 7. State Persistence Format

**JSON for WorkflowState:** Machine-readable, easy to serialize with Pydantic  
**YAML for human-editable config:** Profile configs, provider settings

**Trade-off:** Two formats vs. human-editable state files. We prioritize machine reliability for state, human convenience for config.

### 8. CLI-Only (No HTTP)

**Implementation:** CLI + library interface only

**Rationale:**
- VS Code extension can use subprocess (standard pattern for tools like `black`, `ruff`)
- Focuses one-month timeline on core engine patterns
- Simpler deployment (no server management)
- Works offline
- TypeScript developer can work independently with CLI

**Trade-off:** No web UI or real-time progress updates vs. faster delivery and simpler collaboration.

### 9. File-Based Prompts (Not stdin)

**Decision:** Write prompts to disk rather than streaming via stdin.

**Rationale:**
- Prompts are multi-file bundles (template + standards + schemas)
- Standards bundles are 10k+ characters
- Need to reference attachments by path
- Interactive mode requires persistent artifacts for user review
- Clear audit trail of what was sent to AI

**Trade-off:** More filesystem I/O vs. user visibility and debuggability.

### 10. Planning as First-Class Phase

**Decision:** Keep planning as separate phase before generation.

**Provider role assignments:**
```python
providers = {
    "planner": "gemini",      # Cheap, good at structured thinking
    "generator": "claude",    # Expensive, excellent at code
    "reviewer": "gemini",     # Different perspective
    "reviser": "claude"       # Consistency with generator
}
```

**Benefits:**
- Different AIs for different roles (budget control)
- Plan becomes versioned artifact
- User approval checkpoint in interactive mode
- Can use same AI for both if desired

### 11. Template Organization

**Structure:** Hierarchical by phase, scope-specific files

```
profiles/jpa-mt/templates/
├── planning/
│   ├── domain.md
│   └── vertical.md
├── generation/
│   ├── domain.md
│   └── vertical.md
├── review/
│   ├── domain.md
│   └── vertical.md
└── revision/
    ├── domain.md
    └── vertical.md
```

**Rationale:**
- Easy to compare templates across scopes for same phase
- Natural grouping by workflow stage
- Extensible for new scopes without restructuring

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
10. **Flexible** — Scope/layer system allows custom generation configurations

### Negative

1. **Upfront complexity** — More design work than simple scripts
2. **Learning curve** — New contributors need to understand patterns
3. **Abstraction overhead** — More files/classes than direct implementation
4. **Configuration complexity** — More options than simple flat config

### Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Over-engineering | Focus on patterns that solve real problems; avoid pattern-for-pattern's-sake |
| VS Code extension coupling | Define clear CLI contract; use subprocess (standard practice) |
| State corruption from manual editing | Validate state on load; provide `aiwf validate` command |
| Profile proliferation | Document profile creation guidelines; encourage composition over duplication |
| Standards drift | Immutability enforcement; validation on each iteration |
| Path traversal attacks | Shared PathValidator; all inputs sanitized |

---

## Phase vs State Naming Convention

**Internal Phases** (WorkflowPhase enum):
- Used in domain models and handler chain
- Detailed granularity: `INITIALIZED`, `PLANNING`, `PLANNED`, `PLAN_APPROVED`, `GENERATED`, `REVIEWED`, `REVISED`, `COMPLETE`

**External API States** (CLI output):
- Simplified for user-facing communication
- Examples: `"awaiting_planning_response"`, `"awaiting_generation_response"`, `"completed"`

**Mapping:**
```python
def api_state_from_phase(phase: WorkflowPhase, mode: ExecutionMode) -> str:
    if mode == ExecutionMode.INTERACTIVE:
        return f"awaiting_{phase.value}_response"
    else:
        return f"processing_{phase.value}"
```

**Rationale:**
- Internal phases provide workflow precision
- External states provide user clarity
- Maintains backward compatibility if phases change

---

## Related Decisions

Future ADRs may cover:
- Profile-specific design patterns
- Multi-tenant implementation patterns
- Testing strategy for AI-generated code
- Extension integration patterns

---

## References

- [Martin Fowler - Patterns of Enterprise Application Architecture](https://martinfowler.com/eaaCatalog/)
- [Gang of Four - Design Patterns](https://en.wikipedia.org/wiki/Design_Patterns)
- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

---

**Document Status:** Living document, updated as implementation progresses  
**Last Reviewed:** December 6, 2024  
**Next Review:** After Phase 3 implementation

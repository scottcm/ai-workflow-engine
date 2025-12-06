# ADR-0001: Architecture Overview

Status: Accepted
Date: 2025-01-02
Deciders: Scott

## Context and Problem Statement
We need an AI-assisted development workflow engine that orchestrates multi-phase generation (plan → generate → review → revise), supports interactive/manual workflows as well as automated workflows, persists state, and allows domain-specific "profiles" without modifying core engine logic. A prior workflow, built as Python scripts, demonstrated the core flow but lacked architectural structure, extensibility, and clarity.

This engine is designed to generalize the lessons learned from building real-world AI-assisted development tooling while remaining independent of any proprietary domain logic. It must support legacy-style workflows without adopting their internal designs.

## Decision Drivers
1. Architectural clarity and long-term maintainability.
2. Extensibility through pluggable profiles.
3. Clean, testable boundaries between workflow logic, providers, and templates.
4. Ability to support both interactive (manual copy/paste) and automated (CLI-provider) execution.
5. State persistence to allow resumability and crash recovery.
6. Clear contracts for a VS Code extension.

## Considered Options
### Option 1: Continue Script-Based Workflows
Pros: Already functional; minimal effort.
Cons: No architecture; hard to extend; domain-specific coupling.

### Option 2: Monolithic Engine
Pros: Simple to implement.
Cons: Poor separation of concerns; limited extensibility.

### Option 3: Layered Architecture (Chosen)
Pros: Clean boundaries; extensible via profiles; demonstrates appropriate design patterns; supports multiple execution modes.
Cons: Higher initial design cost.

## Decision Outcome
Adopt a layered architecture using Strategy, Factory, Chain of Responsibility, Command, Builder, Adapter, and Template Method patterns. Introduce profiles that encapsulate workflow-specific templates, standards, and parsing rules.

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
│  - AI Providers, Filesystem, Legacy     │
└─────────────────────────────────────────┘
```

### Core Domain Model
```python
class ExecutionMode(str, Enum):
    INTERACTIVE = "interactive"  # Generate prompts, user pastes manually
    AUTOMATED = "automated"      # Direct AI provider calls

class WorkflowPhase(str, Enum):
    INITIALIZED = "initialized"
    PLANNED = "planned"
    PLAN_APPROVED = "plan_approved"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    REVISED = "revised"
    COMPLETE = "complete"

class WorkflowState(BaseModel):
    session_id: str
    profile: str              # e.g., "jpa-mt-domain"
    phase: WorkflowPhase
    execution_mode: ExecutionMode
    
    # Context
    entity: str
    bounded_context: str | None
    table: str | None
    dev: str | None
    
    # Provider assignments per role
    providers: dict[str, str]  # "planner" -> "gemini", "coder" -> "claude"
    
    # Artifacts by phase
    artifacts: list[Artifact]
    
    # Interactive mode checkpoint
    pending_action: str | None
```

---

## Pattern Justifications

Each pattern solves a specific architectural problem:

### 1. Strategy Pattern (AI Providers)
**Problem**: Need to swap LLM backends (Claude CLI, Gemini CLI, ChatGPT, manual mode) without changing workflow logic.

**Solution**: `AIProvider` interface with concrete implementations.
```python
class AIProvider(ABC):
    async def generate(self, prompt: str, context: dict | None) -> str: ...

# Implementations:
# - ClaudeCliProvider (calls 'claude' CLI)
# - GeminiCliProvider (calls 'gemini' CLI)  
# - ManualProvider (writes prompt to disk, returns placeholder)
```

### 2. Strategy Pattern (Workflow Profiles)
**Problem**: Different code generation domains (ORM, testing, infrastructure) have different templates, standards, and parsing rules.

**Solution**: `WorkflowProfile` interface where profiles are concrete implementations.
```python
class WorkflowProfile(ABC):
    def prompt_template_for(self, phase: WorkflowPhase) -> Path: ...
    def standards_bundle_for(self, context: dict) -> str: ...  # NEW
    def parse_bundle(self, content: str) -> dict[str, str]: ...
    def artifact_dir_for(self, entity: str) -> Path: ...
    def review_config_for(self) -> dict: ...
```
**Note on `standards_bundle_for`:** This method returns the *generated bundle content* 
as a string, not a path. This allows profiles to dynamically assemble standards based on 
context (entity name, workflow phase, etc.) using tag-based selection, templates, or 
other approaches. The profile owns the standards bundling strategy.

### 3. Factory Pattern
**Problem**: Need runtime instantiation of providers and profiles based on configuration.

**Solution**: `ProviderFactory` and `ProfileFactory` with registries.
```python
class ProviderFactory:
    _registry: dict[str, type[AIProvider]] = {
        "claude": ClaudeCliProvider,
        "gemini": GeminiCliProvider,
        "manual": ManualProvider,
    }
    
    @classmethod
    def create(cls, provider_key: str, config: dict) -> AIProvider: ...
    
    @classmethod
    def register(cls, key: str, provider_class: type[AIProvider]): ...
```

### 4. Chain of Responsibility Pattern
**Problem**: Workflow phases (planning, generation, review, revision) need conditional execution based on state, with different chains per profile.

**Solution**: Handler chain where each handler decides whether to process or pass to next.
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
**Problem**: Operations need encapsulation for undo capability, logging, and testability.

**Solution**: Each operation is a command with execute/undo methods.
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
**Problem**: Handler chains are complex to construct—easy to forget a handler or wire them incorrectly.

**Solution**: Fluent `WorkflowBuilder` that constructs valid chains.
```python
chain = (WorkflowBuilder(profile, providers, mode)
    .with_planning()
    .with_generation()
    .with_review()
    .with_revision_loop(max_iterations=2)
    .build())
```

### 7. Adapter Pattern
**Problem**: Need to integrate existing scripts and external tools (CLI agents) without tight coupling.

**Solution**: Adapters wrap external dependencies.
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
**Problem**: Prompts follow a common structure (header, metadata, instructions, standards, context) but vary by profile.

**Solution**: `PromptTemplate` base class with overridable sections.
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
│   └── jpa-mt-domain/           # First profile implementation
│       ├── templates/           # Prompt templates
│       ├── standards/           # Standards bundles
│       └── config.yml           # Profile configuration
├── example-tools/               # Reference implementations
│   └── select_standards.py      # Standards selection pattern
├── docs/
│   ├── adr/                     # Architecture Decision Records
│   ├── architecture.md          # System overview
│   ├── creating-profiles.md     # Profile development guide
│   └── patterns.md              # Pattern catalog
└── tests/
    ├── unit/
    └── integration/
```

---

## Key Architectural Decisions

### 1. Dual Execution Modes (First-Class)

The system explicitly supports two modes:

- **Interactive Mode**: For budget-constrained teams using web UIs
  - Generates prompt files to disk
  - Sets `pending_action` checkpoint in state
  - User manually copies/pastes
  - Resumes from saved state

- **Automated Mode**: For teams with CLI agents or API access
  - Directly calls AI providers
  - Runs entire workflow without manual intervention
  - Still persists state for crash recovery

**Trade-off**: More complexity in handlers (mode-aware behavior) vs. better user experience and future-proofing.

### 2. Profiles Over Configuration

Profiles are **strategies**, not just config files. They encapsulate:
- Template selection logic
- Bundle parsing rules  
- Artifact layout conventions
- Review configuration
- Standards management approach

**Trade-off**: More code per profile vs. proper separation of domain-specific concerns.

### 3. State Persistence Format

- **JSON for WorkflowState**: Machine-readable, easy to serialize with Pydantic
- **YAML for human-editable config**: Profile configs, provider settings

**Trade-off**: Two formats vs. human-editable state files. We prioritize machine reliability for state, human convenience for config.

### 4. CLI-Only (No HTTP)

**Implementation**: CLI + library interface only
**Rationale**:
- VS Code extension can use subprocess (standard pattern for tools like `black`, `ruff`)
- Focuses one-month timeline on core engine patterns
- Simpler deployment (no server management)
- Works offline
- TypeScript developer can work independently with CLI

**Trade-off**: No web UI or real-time progress updates vs. faster delivery and simpler collaboration.

### 5. File-Based Prompts (Not stdin)

**Decision**: Write prompts to disk rather than streaming via stdin.

**Rationale**:
- Prompts are multi-file bundles (template + standards + schemas)
- Standards bundles are 10k+ characters
- Need to reference attachments by path
- Interactive mode requires persistent artifacts for user review
- Clear audit trail of what was sent to AI

**Trade-off**: More filesystem I/O vs. user visibility and debuggability.

### 6. Legacy Script Integration via Adapters

Existing scripts are **not rewritten**, they're **wrapped** as adapters or refactored into commands where appropriate.

**Trade-off**: More abstraction layers vs. preserving working code and demonstrating adapter pattern.

---

## Consequences

### Positive

1. **Extensible**: New profiles without core changes
2. **Testable**: Each layer independently testable
3. **Maintainable**: Clear separation of concerns
4. **Resumable**: Persistent state enables crash recovery
5. **Future-proof**: Architecture supports CLI agents and APIs
6. **Collaborative**: Clear contracts for VS Code extension developer
7. **Language-agnostic**: Core engine supports any target language through profiles

### Negative

1. **Upfront complexity**: More design work than simple scripts
2. **Learning curve**: New contributors need to understand patterns
3. **Abstraction overhead**: More files/classes than direct implementation

### Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Over-engineering | Focus on patterns that solve real problems; avoid pattern-for-pattern's-sake |
| VS Code extension coupling | Define clear CLI contract; use subprocess (standard practice) |
| State corruption from manual editing | Validate state on load; provide `aiwf validate` command |
| Profile proliferation | Document profile creation guidelines; encourage composition over duplication |

---

## Implementation Plan

### Phase 1: Foundation (Week 1)
- [ ] Core models (`WorkflowState`, `Artifact`, enums)
- [ ] `WorkflowProfile` and `AIProvider` interfaces
- [ ] `ProviderFactory` and `ProfileFactory`
- [ ] Basic state persistence (load/save)

### Phase 2: First Profile (Week 2)
- [ ] `JpaMtDomainProfile` implementation
- [ ] Create prompt templates
- [ ] Standards bundle management
- [ ] `ManualProvider` (for interactive mode)

### Phase 3: Patterns & Pipeline (Week 3)
- [ ] Commands (prepare, extract, review, revise)
- [ ] Handlers (planning, generation, review, revision loop)
- [ ] `WorkflowBuilder`
- [ ] `WorkflowExecutor`

### Phase 4: CLI & Polish (Week 4)
- [ ] CLI commands (`new`, `run`, `step`, `resume`, `status`, `list`, `profiles`)
- [ ] Integration tests
- [ ] Documentation
- [ ] Extension API contract documentation

---

## Related Decisions

- ADR-0002: Profile Architecture (domain vs vertical separation)
- ADR-0003: Standards Management as Profile Responsibility
- ADR-0004: Multi-Tenant First Approach
- ADR-0005: File-Based Prompts vs stdin

---

## References

- [Martin Fowler - Patterns of Enterprise Application Architecture](https://martinfowler.com/eaaCatalog/)
- [Gang of Four - Design Patterns](https://en.wikipedia.org/wiki/Design_Patterns)
- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

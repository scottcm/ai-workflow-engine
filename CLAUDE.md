# CLAUDE.md

AI agent guide for the AI Workflow Engine codebase.

## Project Overview

Python CLI tool that orchestrates multi-phase AI-assisted code generation workflows. Supports both manual mode (user copies prompts to AI, pastes responses back) and automated mode (AI providers invoked directly). Engine handles state, files, approvals.

## Directory Structure

```
ai-workflow-engine/
├── aiwf/                        # Main package
│   ├── domain/
│   │   ├── models/              # Pydantic models
│   │   │   ├── workflow_state.py    # WorkflowState, WorkflowPhase, WorkflowStatus, Artifact
│   │   │   ├── processing_result.py # ProcessingResult (profile return type)
│   │   │   └── write_plan.py        # WritePlan, WriteOp
│   │   ├── profiles/            # Profile abstractions
│   │   │   ├── workflow_profile.py  # WorkflowProfile ABC
│   │   │   └── profile_factory.py   # ProfileFactory registry
│   │   ├── providers/           # AI provider abstractions
│   │   │   ├── ai_provider.py       # AIProvider ABC (validate, generate)
│   │   │   ├── provider_factory.py  # ProviderFactory registry
│   │   │   └── manual_provider.py   # ManualProvider (returns None)
│   │   ├── errors.py            # ProviderError exception
│   │   ├── persistence/
│   │   │   └── session_store.py     # SessionStore (JSON file I/O)
│   │   └── validation/
│   │       └── path_validator.py    # PathValidator utilities
│   ├── application/             # Orchestration logic
│   │   ├── workflow_orchestrator.py # Main engine - step(), approve()
│   │   ├── approval_handler.py      # Approval logic, run_provider()
│   │   ├── approval_specs.py        # STUB - being replaced by TransitionTable
│   │   ├── config_loader.py         # YAML config loading
│   │   └── standards_materializer.py
│   └── interface/
│       └── cli/
│           ├── cli.py               # Click commands
│           └── output_models.py     # JSON output Pydantic models
├── profiles/                    # Profile implementations (outside aiwf/)
│   └── jpa_mt/
│       ├── jpa_mt_profile.py        # JpaMtProfile implementation
│       ├── jpa_mt_config.py         # Pydantic config model
│       ├── jpa_mt_standards_provider.py
│       ├── config.yml               # Profile configuration (gitignored)
│       ├── bundle_extractor.py      # Code extraction from responses
│       ├── review_metadata.py       # @@@REVIEW_META parsing
│       └── templates/               # Prompt templates with {{include:}}
├── docs/
│   ├── adr/                     # Architecture Decision Records
│   └── plans/                   # Implementation plans
├── tests/
│   ├── unit/                    # Mirrors aiwf/ structure
│   └── integration/             # End-to-end workflow tests
└── .aiwf/                       # Runtime session storage (gitignored)
    └── sessions/
        └── {session-id}/
            ├── session.json
            ├── standards-bundle.md
            ├── plan.md
            └── iteration-N/
                ├── *-prompt.md
                ├── *-response.md
                └── code/
```

## Key Concepts

### Phase + Stage Model (ADR-0012)

**Phases** describe WHAT work is being done:
- `INIT` - Session created (transient, immediately proceeds to PLAN)
- `PLAN` - Creating implementation plan
- `GENERATE` - Generating code artifacts (creates iteration-1/)
- `REVIEW` - Reviewing generated code
- `REVISE` - Revising based on feedback (creates iteration-N/)
- `COMPLETE`, `ERROR`, `CANCELLED` - Terminal states

**Stages** describe WHAT we're working on within active phases:
- `PROMPT` - Prompt is created, editable, awaiting approval
- `RESPONSE` - Response is created, editable, awaiting approval

Flow: `PLAN[PROMPT]` → approve → `PLAN[RESPONSE]` → approve → `GENERATE[PROMPT]` → ...

**Key insight:** `approve` causes stage transitions. Work happens AFTER entering the new stage.

### Commands

- `init` - Create session, immediately enter PLAN[PROMPT], create planning prompt
- `approve` - Approve current artifact, transition to next stage/phase
- `reject` - Reject with feedback, stay in current stage for edits
- `retry` - Request regeneration with feedback
- `cancel` - Terminate workflow

**Approve transitions. Work follows.**

### Responsibility Boundaries

| Component | Does | Does Not |
|-----------|------|----------|
| Profile | Generate prompts, parse responses, return WritePlan | File I/O, mutate state |
| Engine | Execute WritePlan, all file I/O, compute hashes, add path prefixes | Generate prompts, parse responses |
| Provider | Accept prompt string, return response string (or None for manual) | File I/O |

**WritePlan Path Contract:**
- Profiles return filename-only or relative paths in WritePlan (e.g., `Customer.java` or `entity/Customer.java`)
- Engine adds the `iteration-{N}/code/` prefix when writing artifacts
- Engine normalizes legacy paths that include iteration prefixes
- Engine validates paths: no traversal, no absolute paths, no hidden files, no protected files

### AI Providers

Providers enable automated workflow execution. Key points:
- `validate()` called during `initialize_run()` - fail fast before workflow starts
- `generate()` returns response string, or `None` for manual mode
- `ProviderError` propagates to orchestrator's `approve()` which sets ERROR status
- Timeouts configured in provider metadata (see ADR-0007)

See [docs/provider-implementation-guide.md](docs/provider-implementation-guide.md) for implementation details.

### Execution Mode vs Providers

Two orthogonal concerns:
- **Execution Mode** (control flow): `INTERACTIVE` = user issues step/approve, `AUTOMATED` = engine auto-advances
- **Providers** (data flow): `manual` = external response file, `claude`/`gemini` = API produces response

Key insight: "Manual provider" ≠ "Interactive mode". Example: `INTERACTIVE + claude` means user controls *when* to advance, Claude produces *what*.

### Data Flow

1. Engine calls `profile.generate_*_prompt(context)` → string
2. Engine writes prompt file
3. User/provider supplies response file
4. Engine calls `profile.process_*_response(content, ...)` → ProcessingResult
5. Engine executes `result.write_plan`
6. Engine updates state

### State Transitions (ADR-0012 In Progress)

The approval logic is being rewritten as a declarative `TransitionTable`. Stage transitions work as follows:

```
PHASE[PROMPT] ──approve──► PHASE[RESPONSE] ──approve──► NEXT_PHASE[PROMPT]
       │                         │
       └── prompt editable       └── AI called, response editable
```

Work happens AFTER entering the new stage:
- Approve PROMPT → enter RESPONSE → AI produces response → user can edit
- Approve RESPONSE → enter next PHASE[PROMPT] → prompt created → user can edit

**REVIEW[RESPONSE] is special:** The review contains a verdict (PASS/FAIL) that determines COMPLETE vs REVISE. The `--complete` and `--revise` flags allow user override when disagreeing with the verdict.

See ADR-0012 for full transition table and resolved design decisions.

## Conventions

### Pydantic

All data classes use Pydantic `BaseModel`, not dataclasses:
- Use `Field(default_factory=list)` for mutable defaults, not `field()`
- Use `str | None = None` for optional fields
- Use `Field(..., exclude=True)` to exclude from serialization

### Naming

- Private methods: `_method_name`
- Phase without -ing suffix in filenames: `planning-prompt.md`, not `planning-ing-prompt.md`
- Test files mirror source: `test_workflow_orchestrator.py`

### Error Handling

- `last_error` on WorkflowState for recoverable errors
- `error` in CLI output for command-level failures
- Both can appear in same response

### File Patterns

Prompt/response files:
- `planning-prompt.md`, `planning-response.md`
- `generation-prompt.md`, `generation-response.md`
- `review-prompt.md`, `review-response.md`
- `revision-prompt.md`, `revision-response.md`

### Commit Messages

Format:
```
type(scope): summary line

- Single-level bullets only (no sub-bullets)
- Each bullet is single-line text
- No section headers unless commit is complex
```

Keep it simple. No Claude co-author citations.

## ADRs

Architecture decisions in `docs/adr/`:

| ADR | Status | Summary |
|-----|--------|---------|
| 0001 | Accepted | Architecture overview, patterns (Strategy, Factory, Repository, State) |
| 0002 | Accepted | Template layering with {{include:}} directives |
| 0003 | Accepted | Pydantic for workflow state validation |
| 0004 | Accepted | Structured review metadata (@@@REVIEW_META) |
| 0005 | Accepted | Chain of Responsibility for approval handling |
| 0006 | Accepted | Observer pattern for workflow events |
| 0007 | Draft | Plugin architecture (AI providers, standards providers) |
| 0008 | Draft | Configuration management |
| 0009 | Draft | Session state schema versioning |
| 0012 | Draft | Phase+Stage model, approval providers, TransitionTable |

## Extension Points

| To Add | Location | Pattern |
|--------|----------|---------|
| CLI command | `cli.py`, `output_models.py` | Click command + Pydantic output model |
| Workflow profile | `profiles/` directory | Implement `WorkflowProfile` ABC, register in factory |
| AI provider | `domain/providers/` | Implement `AIProvider` ABC, register in factory |
| Standards provider | Profile-specific | Implement provider interface per profile needs |

See [docs/provider-implementation-guide.md](docs/provider-implementation-guide.md) for AI provider details.

## Don'ts

- Profiles never do file I/O
- Profiles never mutate WorkflowState
- Don't use `field()` - use `Field()` (Pydantic, not dataclass)
- Don't change step() return signature (breaking API change)
- Don't block workflow on hash mismatches (non-enforcement policy)
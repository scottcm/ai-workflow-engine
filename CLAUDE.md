# CLAUDE.md

AI agent guide for the AI Workflow Engine codebase.

## Environment

- **Platform:** Windows
- **Python:** 3.13+ via Poetry
- **Run tests:** `poetry run pytest tests/unit/ -v`
- **Run CLI:** `poetry run aiwf <command>`

## Context Recovery

**After context compression, ALWAYS read `claude-code-provider-work.md` first.**

This working document tracks in-progress implementation state that would otherwise be lost during compression. It contains:
- Current implementation phase and status
- Key decisions made during implementation
- Files changed and why
- Next steps if work continues

## Quick Reference

```
# Run all unit tests
poetry run pytest tests/unit/ -v

# Run specific test file
poetry run pytest tests/unit/domain/providers/test_claude_code_provider.py -v

# Skip integration tests requiring Claude CLI
poetry run pytest -m "not claude_code"

# Check git status
git status
```

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
│   │   │   ├── provider_result.py   # ProviderResult (provider return type)
│   │   │   └── write_plan.py        # WritePlan, WriteOp
│   │   ├── profiles/            # Profile abstractions
│   │   │   ├── workflow_profile.py  # WorkflowProfile ABC
│   │   │   └── profile_factory.py   # ProfileFactory registry
│   │   ├── providers/           # Response provider abstractions
│   │   │   ├── response_provider.py # ResponseProvider ABC (validate, generate)
│   │   │   ├── provider_factory.py  # ResponseProviderFactory registry
│   │   │   ├── manual_provider.py   # ManualProvider (returns None)
│   │   │   └── claude_code_provider.py # ClaudeCodeProvider (SDK-based)
│   │   ├── errors.py            # ProviderError exception
│   │   ├── persistence/
│   │   │   └── session_store.py     # SessionStore (JSON file I/O)
│   │   └── validation/
│   │       └── path_validator.py    # PathValidator utilities
│   ├── application/             # Orchestration logic
│   │   ├── workflow_orchestrator.py # Main engine - step(), approve()
│   │   ├── approval_handler.py      # run_provider() utility
│   │   └── config_loader.py         # YAML config loading
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
    └── sessions/{session-id}/
```

## Key Concepts

### Responsibility Boundaries

| Component | Does | Does Not |
|-----------|------|----------|
| Profile | Generate prompts, parse responses, return WritePlan | File I/O, mutate state |
| Engine | Execute WritePlan, validate provider results, compute hashes | Generate prompts, parse responses |
| Provider | Accept prompt, return ProviderResult (or None for manual) | Mutate state |

### Phase + Stage Model (ADR-0012)

**Phases:** INIT → PLAN → GENERATE → REVIEW → REVISE → COMPLETE/ERROR/CANCELLED

**Stages:** PROMPT (editable, awaiting approval) → RESPONSE (AI produces, editable)

Flow: `PLAN[PROMPT]` → approve → `PLAN[RESPONSE]` → approve → `GENERATE[PROMPT]` → ...

**Key insight:** `approve` causes stage transitions. Work happens AFTER entering the new stage.

### AI Providers

Providers enable automated workflow execution:
- `ResponseProviderFactory.create("claude-code")` - creates provider instance
- `validate()` called during `initialize_run()` - fail fast before workflow starts
- `generate()` returns `ProviderResult` with `files: dict[str, str | None]`
- `None` value in files dict = provider wrote file directly (local-write)
- String value = content for engine to write (API-only providers)
- `fs_ability` metadata: `local-write`, `local-read`, `none`

**Registered providers:** `manual`, `claude-code`

### Data Flow

1. Engine calls `profile.generate_*_prompt(context)` → string
2. Engine writes prompt file
3. User/provider supplies response
4. Engine calls `profile.process_*_response(content, ...)` → ProcessingResult
5. Engine executes `result.write_plan`
6. Engine updates state

## Conventions

### Pydantic

All data classes use Pydantic `BaseModel`, not dataclasses:
- Use `Field(default_factory=list)` for mutable defaults
- Use `str | None = None` for optional fields
- Use `Field(..., exclude=True)` to exclude from serialization

### Naming

- Private methods: `_method_name`
- Phase without -ing suffix: `planning-prompt.md`, not `planning-ing-prompt.md`
- Test files mirror source: `test_workflow_orchestrator.py`

### Commit Messages

```
type(scope): summary line

- Single-level bullets only (no sub-bullets)
- Each bullet is single-line text
```

Keep it simple. No Claude co-author citations.

## ADRs

| ADR | Status | Summary |
|-----|--------|---------|
| 0001 | Accepted | Architecture overview, patterns (Strategy, Factory, Repository, State) |
| 0002 | Accepted | Template layering with {{include:}} directives |
| 0003 | Accepted | Pydantic for workflow state validation |
| 0004 | Accepted | Structured review metadata (@@@REVIEW_META) |
| 0005 | Superseded | Chain of Responsibility (replaced by ADR-0012) |
| 0006 | Accepted | Observer pattern for workflow events |
| 0007 | Draft | Plugin architecture (AI providers, standards providers) |
| 0008 | Draft | Configuration management |
| 0009 | Draft | Session state schema versioning |
| 0012 | Accepted | Phase+Stage model, TransitionTable state machine |
| 0013 | Accepted | Claude Code provider via Agent SDK |

## Extension Points

| To Add | Location | Pattern |
|--------|----------|---------|
| CLI command | `cli.py`, `output_models.py` | Click command + Pydantic output model |
| Workflow profile | `profiles/` directory | Implement `WorkflowProfile` ABC, register in factory |
| Response provider | `domain/providers/` | Implement `ResponseProvider` ABC, register in `ResponseProviderFactory` |

## Don'ts

- Profiles never do file I/O
- Profiles never mutate WorkflowState
- Don't use `field()` - use `Field()` (Pydantic, not dataclass)
- Don't change step() return signature (breaking API change)
- Don't block workflow on hash mismatches (non-enforcement policy)

# CLAUDE.md

AI agent guide for the AI Workflow Engine codebase.

## Environment

- **Platform:** Windows
- **Python:** 3.13+ via Poetry
- **Run tests:** `poetry run pytest tests/unit/ -v`
- **Run CLI:**
  ```bash
  # Initialize workflow session
  poetry run aiwf init jpa-mt -c entity=X -c table=Y -c bounded-context=Z -c scope=domain -c schema-file=PATH

  # Profile-specific commands (jpa-mt example)
  poetry run aiwf jpa-mt scopes
  poetry run aiwf jpa-mt info

  # Generic workflow commands
  poetry run aiwf approve <session-id>
  poetry run aiwf reject <session-id>
  poetry run aiwf status <session-id>
  poetry run aiwf list
  ```

## Working Documents

Two documents preserve state across context boundaries:

| Document | Purpose | Lifespan |
|----------|---------|----------|
| `memory.md` | Session progress, active task, what's done | Per-task, prune often |
| `knowledge.md` | Stable facts, decisions, file locations | Long-term reference |

### Context Recovery Protocol

**After context compression, ALWAYS:**
1. Read `memory.md` FIRST (current task state)
2. Read `knowledge.md` if needed (reference facts)
3. Update Active Task before starting work
4. Prune completed items from memory.md

### Memory File Lifecycle

```
1. START: Read memory.md, update Active Task
2. WORK: Update progress as you go
3. LEARN: Add discoveries to Reference Knowledge
4. FINISH: Clear Active Task, prune Status to last 5 items
```

### Required Sections in memory.md

| Section | Purpose | Persistence |
|---------|---------|-------------|
| **Active Task** | Current work (ONE task only) | Clear when done |
| **Decisions** | Why X was chosen | Keep with rationale |
| **Reference Knowledge** | Session-specific facts | Move to knowledge.md when stable |
| **Status** | Completed items | Prune to last 5 |

### Keeping Memory Small

- ONE active task at a time
- Prune Status section aggressively (last 5 items)
- Move stable facts from Reference Knowledge to knowledge.md
- Remove detailed approach steps after completion

## Quick Reference

```bash
# Run all unit tests (before commit only)
poetry run pytest tests/unit/ -q --tb=no

# Run specific test file (after editing a file)
poetry run pytest tests/unit/domain/providers/test_claude_code_provider.py -v

# Run tests matching keyword
poetry run pytest -k "approval" -v

# Skip integration tests requiring external CLIs
poetry run pytest -m "not claude_code and not gemini_cli"
```

## Test Strategy

**Do NOT run the full test suite after every change.** This wastes time and context.

| When | What to Run | Why |
|------|-------------|-----|
| After editing a file | Matching test file only | Fast feedback, minimal context |
| After changing orchestrator | `tests/unit/application/` | Tests related subsystem |
| After changing a provider | `tests/unit/domain/providers/test_<provider>.py` | Targeted validation |
| Before commit | `pytest tests/unit/ -q --tb=no` | Full validation, minimal output |
| Integration tests | Only when explicitly requested | Require external CLIs |

**Output guidelines:**
- Use `-q` (quiet) to reduce output
- Use `--tb=no` for pass/fail only (no tracebacks unless debugging)
- Report counts: "45 passed, 2 failed" not full test output
- Show full output only for failures

**Rationale:** Full suite is 850+ tests. Running all after every edit consumes context and time. Targeted tests catch issues faster. (rejected: running full suite after every change)

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
│   │   │   ├── ai_provider_result.py # AIProviderResult (provider return type)
│   │   │   └── write_plan.py        # WritePlan, WriteOp
│   │   ├── profiles/            # Profile abstractions
│   │   │   ├── workflow_profile.py  # WorkflowProfile ABC
│   │   │   └── profile_factory.py   # ProfileFactory registry
│   │   ├── providers/           # AI provider abstractions
│   │   │   ├── ai_provider.py       # AIProvider ABC (validate, generate)
│   │   │   ├── provider_factory.py  # AIProviderFactory registry
│   │   │   ├── manual_provider.py   # ManualAIProvider (returns None)
│   │   │   └── claude_code_provider.py # ClaudeCodeAIProvider (SDK-based)
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
│       ├── __init__.py              # Profile registration and CLI commands
│       ├── profile.py               # JpaMtProfile implementation
│       ├── config.py                # Pydantic config model
│       ├── standards.py             # Standards provider
│       ├── config.yml               # Profile configuration (gitignored)
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
| Provider | Accept prompt, return AIProviderResult (or None for manual) | Mutate state |

### Phase + Stage Model (ADR-0012)

**Phases:** INIT → PLAN → GENERATE → REVIEW → REVISE → COMPLETE/ERROR/CANCELLED

**Stages:** PROMPT (editable, awaiting approval) → RESPONSE (AI produces, editable)

Flow: `PLAN[PROMPT]` → approve → `PLAN[RESPONSE]` → approve → `GENERATE[PROMPT]` → ...

**Key insight:** `approve` causes stage transitions. Work happens AFTER entering the new stage.

### AI Providers

Providers enable automated workflow execution:
- `AIProviderFactory.create("claude-code")` - creates provider instance
- `validate()` called during `initialize_run()` - fail fast before workflow starts
- `generate()` returns `AIProviderResult` with `files: dict[str, str | None]`
- `None` value in files dict = provider wrote file directly (local-write)
- String value = content for engine to write (API-only providers)
- `fs_ability` metadata: `local-write`, `local-read`, `write-only`, `none`

**Registered providers:** `manual`, `claude-code`, `gemini-cli`

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
| 0003 | Accepted | Pydantic for workflow state validation |
| 0004 | Accepted | Structured review metadata (@@@REVIEW_META) |
| 0006 | Accepted | Observer pattern for workflow events |
| 0007 | Accepted | Plugin architecture (AI providers, standards providers) |
| 0008 | Accepted | Engine-Profile separation of concerns |
| 0009 | Draft | Prompt structure and AI provider capabilities |
| 0010 | Accepted | Profile access to AI providers |
| 0011 | Draft | Prompt Builder API |
| 0012 | Accepted | Phase+Stage model, TransitionTable state machine |
| 0013 | Accepted | Claude Code provider via Agent SDK |
| 0014 | Accepted | Gemini CLI provider |
| 0015 | Accepted | Approval provider implementation |
| 0016 | Accepted | V2 workflow config and provider naming |
| 0017 | Proposed | Plugin dependency injection |
| 0018 | Proposed | JPA-MT test generation scopes |

## Extension Points

| To Add | Location | Pattern |
|--------|----------|---------|
| CLI command | `cli.py`, `output_models.py` | Click command + Pydantic output model |
| Workflow profile | `profiles/` directory | Implement `WorkflowProfile` ABC, register in factory |
| AI provider | `domain/providers/` | Implement `AIProvider` ABC, register in `AIProviderFactory` |

## Don'ts

- Profiles never do file I/O
- Profiles never mutate WorkflowState
- Don't use `field()` - use `Field()` (Pydantic, not dataclass)
- Don't change step() return signature (breaking API change)
- Don't block workflow on hash mismatches (non-enforcement policy)

## Behavioral Rules

1. **Ask before implementing** - When there are multiple valid approaches, present options with your recommendation, then wait for user choice.

2. **Stop and re-read when corrected** - If the user corrects you, don't continue with your assumption. Re-read what they actually said.

3. **Don't persist on corrected topics** - When the user says "not X", stop referencing X. Don't keep bringing it back.

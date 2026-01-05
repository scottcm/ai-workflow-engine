# CLAUDE.md

AI agent guide for the AI Workflow Engine codebase.

## Environment

- **Platform:** Windows
- **Python:** 3.13+ via Poetry
- **Run tests:** `poetry run pytest tests/unit/ -v`
- **Run CLI:** `poetry run aiwf <command>`

## Context Recovery and Working Documents

**After context compression, ALWAYS read the active working document first.**

Working documents (e.g., `claude-code-provider-work.md`) preserve implementation state across context boundaries. They are critical for maintaining continuity.

### Working Document Structure

| Section | Purpose |
|---------|---------|
| **Current Status** | Quick scan of what's done vs in-progress |
| **Implementation Summary** | Files changed, with descriptions |
| **Code Review Findings** | What was reviewed, what was fixed |
| **Design Rationale** | WHY decisions were made, including rejected alternatives |
| **Next Steps** | Pending work items |

### How to Use Working Documents

1. **Read first** - Before any implementation work, read the working document to recover context
2. **Check Design Rationale** - Before proposing changes, verify you're not re-proposing rejected approaches
3. **Update incrementally** - Update the working file BEFORE and AFTER each piece of work, not at end of session
4. **Include "why"** - For each decision, capture the reasoning; for rejected alternatives, note `(rejected: reason)`
5. **Keep current** - Mark completed items, update test counts, note pending work

### When to Update Working Documents

| Trigger | Action |
|---------|--------|
| Design decision made | Add to Decisions table with rationale + rejected alternatives |
| Implementation complete | Add to Implementation Status table |
| Bug found/fixed | Add to Bugs Fixed table |
| Test verification | Note pass count |
| Task started | Mark as in-progress |
| Task done | Mark as complete |

**Why incremental updates matter:** Context compression loses mental state. The working file is external memory. If you batch updates at end of session, you risk losing work if context compresses mid-task.

### Design Rationale Format

Use this table format to preserve decision context:

```markdown
| Decision | Why |
|----------|-----|
| Gate before hash | Content must be approved before becoming immutable (rejected: hash-then-approve) |
| Skip retry for PROMPT | Prompts are profile-generated, not AI-generated (rejected: profile regeneration) |
```

The `(rejected: X)` suffix prevents re-proposing dismissed approaches after context compression.

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

**Rationale:** Full suite is 777+ tests. Running all after every edit consumes context and time. Targeted tests catch issues faster. (rejected: running full suite after every change)

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
- `fs_ability` metadata: `local-write`, `local-read`, `none`

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
| AI provider | `domain/providers/` | Implement `AIProvider` ABC, register in `AIProviderFactory` |

## Don'ts

- Profiles never do file I/O
- Profiles never mutate WorkflowState
- Don't use `field()` - use `Field()` (Pydantic, not dataclass)
- Don't change step() return signature (breaking API change)
- Don't block workflow on hash mismatches (non-enforcement policy)

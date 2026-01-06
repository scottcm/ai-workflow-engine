# CLAUDE.md

AI agent guide for the AI Workflow Engine codebase.

## Environment

- **Platform:** Windows
- **Python:** 3.13+ via Poetry
- **Run tests:** `poetry run pytest tests/unit/ -v`
- **Run CLI:**
  ```bash
  # Profile-specific commands (jpa-mt example)
  poetry run aiwf jpa-mt init --entity X --table Y --bounded-context Z --scope domain --schema-file PATH
  poetry run aiwf jpa-mt scopes
  poetry run aiwf jpa-mt info

  # Generic workflow commands
  poetry run aiwf step <session-id>
  poetry run aiwf approve <session-id>
  poetry run aiwf reject <session-id>
  poetry run aiwf status <session-id>
  poetry run aiwf list
  ```

## Context Recovery and Working Documents

**After context compression, ALWAYS read the active working document first.**

Working documents (e.g., `claude-code-provider-work.md`) preserve implementation state across context boundaries. They are critical for maintaining continuity.

### Working Document Structure

| Section | Purpose |
|---------|---------|
| **Active Task** | REQUIRED - What you're doing RIGHT NOW (see below) |
| **Decisions Made** | WHY decisions were made, including rejected alternatives |
| **Implementation Status** | What's done, what's pending |

### Active Task Section (CRITICAL)

Every working document MUST have an Active Task section near the top:

```markdown
## Active Task

**Doing:** [current task - what you're about to do]
**Why:** [context and reasoning]
**Blocked by:** [if waiting on something, otherwise omit]
```

**Protocol:**
1. BEFORE starting work: Write what you're about to do in Active Task
2. DO the work
3. AFTER completing: Clear Active Task, add outcome to relevant section (Decisions, Status, etc.)

**Why this matters:** Context compression loses your mental state. If you only write results AFTER work, compression mid-task means you forget what you were doing. Writing intent FIRST creates a breadcrumb.

### How to Use Working Documents

1. **Read Active Task first** - This tells you what was in progress
2. **Check Decisions** - Don't re-propose rejected approaches
3. **Write intent before action** - Update Active Task BEFORE starting work
4. **Clear when done** - Move outcomes to appropriate sections, clear Active Task

### Decisions Format

Active decisions table:

```markdown
## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use absolute paths | AI needs to find files regardless of working directory |
| D2 | Profile describes format, engine controls destination | Separation of concerns |
```

When a decision is deprecated/changed, move it to Deprecated section:

```markdown
## Deprecated Decisions

| # | Was | Changed To | Why |
|---|-----|------------|-----|
| D1 | Relative paths | D1 (absolute) | AI launched from wrong dir couldn't resolve paths |
```

**Maintenance:** Periodically review Decisions table. If any no longer apply, move to Deprecated with explanation. The "Changed To" column links to the replacement decision.

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

## Behavioral Rules

1. **Ask before implementing** - When there are multiple valid approaches, present options with your recommendation, then wait for user choice.

2. **Stop and re-read when corrected** - If the user corrects you, don't continue with your assumption. Re-read what they actually said.

3. **Don't persist on corrected topics** - When the user says "not X", stop referencing X. Don't keep bringing it back.

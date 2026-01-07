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

Working documents (e.g., `workflow-process-analysis.md`) preserve implementation state across context boundaries. They prevent costly re-discovery of codebase knowledge.

### Working Document Lifecycle

```
1. PLAN: Write what you're about to do, why, and how
2. EXECUTE: Do the work, update progress as you go
3. RECORD: Add results/findings to permanent sections
4. CLEAN: Remove detailed plan steps, keep only what's needed for context
```

### Required Sections

| Section | When to Write | Purpose |
|---------|---------------|---------|
| **Active Task** | BEFORE starting | What you're doing, why, next steps |
| **Reference Knowledge** | After research | Permanent facts that shouldn't be re-discovered |
| **Decisions** | When choices are made | Why X was chosen, what was rejected |
| **Status** | After completing items | What's done, what's pending |

### Active Task Section (CRITICAL)

```markdown
## Active Task

**Question:** What are you trying to answer/accomplish?
**Why:** Context and motivation
**Approach:**
1. Step I will take first
2. Step I will take second
3. ...

**Progress:**
- [x] Step 1 complete - found X
- [ ] Step 2 in progress
```

**Protocol:**
1. BEFORE starting: Write question, why, and approach steps
2. DURING work: Check off steps, note findings
3. AFTER completing: Move findings to Reference Knowledge, clear Active Task

### Reference Knowledge Section

**Purpose:** Store facts that required code exploration so they don't need re-discovery.

```markdown
## Reference Knowledge

### Approval Gates (ADR-0012, ADR-0015)

Each gate asks a specific question:
| Phase | Stage | Question |
|-------|-------|----------|
| PLAN | PROMPT | "Is this planning prompt ready to send to AI?" |
| PLAN | RESPONSE | "Is this plan acceptable?" |
...

Key behavior: Gates run AFTER content creation, not when user issues `approve`.

### Where Things Are Configured

| Concept | Location | Notes |
|---------|----------|-------|
| open_questions_mode | profiles/jpa_mt/config.py | Controls response content, not workflow |
| ApprovalConfig | aiwf/application/approval_config.py | Per-stage gate configuration |
```

### Decisions Format

```markdown
## Decisions

| # | Decision | Rationale | Alternatives Rejected |
|---|----------|-----------|----------------------|
| D1 | Use ApprovalConfig, not ExecutionMode | ApprovalConfig is granular per-stage | ExecutionMode is unused, binary |
```

### Cleanup Guidelines

After completing a task:
1. **Keep:** Reference Knowledge (permanent facts)
2. **Keep:** Decisions with rationale
3. **Remove:** Detailed approach steps (they're done)
4. **Summarize:** Reduce verbose findings to key points

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

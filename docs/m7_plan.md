# M7 Plan — Workflow Semantics, Artifacts, Approvals, and Hashing

## Purpose

M7 stabilizes the AI Workflow Engine after architectural drift during M6.
The goal is to:
- enforce clear responsibility boundaries,
- solidify file-materialized workflow semantics,
- introduce explicit approval checkpoints,
- enable hashing for auditability, deduplication, and UX,
- and unblock forward development.

This document is authoritative for M7 execution.

---

## Status

**M7 is COMPLETE.** This document reflects the implemented behavior.

Completed slices:
- 7A: Core domain model contracts
- 7B: Approval system with deferred hashing
- 7C: REVIEWED approval gate

---

## Core Workflow Model

### Phase Structure

The workflow consists of the following phases:

**WorkflowPhase Enum:**
```python
class WorkflowPhase(str, Enum):
    INITIALIZED = "initialized"
    
    # Planning
    PLANNING = "planning"      # *ING: prompt issued, awaiting response
    PLANNED = "planned"        # *ED: response received, awaiting approval
    
    # Generation
    GENERATING = "generating"  # *ING: prompt issued, processes response, extracts code
    GENERATED = "generated"    # *ED: gates on artifact hashes (approval required)
    
    # Review
    REVIEWING = "reviewing"    # *ING: prompt issued, awaiting response
    REVIEWED = "reviewed"      # *ED: gates on review_approved, then processes verdict
    
    # Revision
    REVISING = "revising"      # *ING: prompt issued, processes response, extracts code
    REVISED = "revised"        # *ED: gates on artifact hashes (approval required)
    
    # Terminal
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"
```

### Phase Responsibility Split (As Implemented)

**PLANNING, REVIEWING (ING phases):**
- Prompt issuance if missing
- Gate on response file existence
- Transition to ED phase when response exists
- No response processing

**GENERATING, REVISING (ING phases with processing):**
- Prompt issuance if missing
- When response exists: process response, extract code, write artifacts
- Transition to ED phase
- Note: This deviates from pure ING/ED split but works correctly

**PLANNED, GENERATED, REVISED, REVIEWED (ED phases):**
- Gate on approval state
- PLANNED: gates on `plan_approved`
- GENERATED/REVISED: gates on all artifacts having `sha256` set
- REVIEWED: gates on `review_approved`, then processes verdict

### Loop Semantics

- **PLANNING** happens once per session.
- **GENERATING** happens once per session.
- The only loop is **REVIEWING ⇄ REVISING**.
- A revision may be incremental or a complete rewrite.
- The engine does not distinguish between "small" and "large" revisions.

If foundational inputs (standards or approved plan) need to change, a **new session is required**.

---

## Iteration Numbering

Iterations are **1-indexed**:

- `iteration-1`: First generation
- `iteration-2`: First revision (if review fails)
- `iteration-N`: (N-1)th revision

### Iteration Increment Rule

Iteration increments **only** when transitioning REVIEWED → REVISING.

The iteration number remains stable across:
- GENERATING → GENERATED → REVIEWING → REVIEWED (all iteration-1)
- REVISING → REVISED → REVIEWING → REVIEWED (all iteration-N)

---

## Files Are the Workflow Contract

This engine is intentionally **file-materialized**.

### Invariant

> A phase is complete only if its required files exist on disk.

If a required file is missing:
- there is no artifact,
- the phase is incomplete,
- the workflow must not advance.

### Canonical File Locations

**Session-Scoped Files:**
```
.aiwf/sessions/{session-id}/
├── session.json             # Workflow state
├── standards-bundle.md      # Created at init, immutable
└── plan.md                  # Created in PLANNED, hashed on approval
```

**Iteration-Scoped Files:**
```
.aiwf/sessions/{session-id}/
├── iteration-1/
│   ├── planning-prompt.md
│   ├── planning-response.md
│   ├── generation-prompt.md
│   ├── generation-response.md
│   ├── code/
│   │   ├── Tier.java
│   │   └── TierRepository.java
│   ├── review-prompt.md
│   └── review-response.md
│
└── iteration-2/              # Created only if revision needed
    ├── revision-prompt.md
    ├── revision-response.md
    ├── code/
    │   ├── Tier.java         # Revised
    │   └── TierRepository.java
    ├── review-prompt.md
    └── review-response.md
```

Filenames are intentional and semantic. They are part of the workflow contract and must not be treated as incidental.

---

## Artifact Definition

An **artifact** is:
- something produced during a workflow run,
- materialized on disk,
- required for correctness, progression, auditability, or user feedback.

Artifacts are not optional.

### Artifact Metadata (Minimal)

Workflow state tracks **metadata only**, never content:

```python
class Artifact(BaseModel):
    path: str                 # "iteration-1/code/Tier.java"
    phase: WorkflowPhase      # GENERATING, REVISING (phase when written)
    iteration: int            # 1, 2, 3, ...
    sha256: str | None        # None until approved, then file hash
    created_at: datetime      # When created
```

There are **no ArtifactKind or ArtifactRole enums** in M7.
Semantics are encoded via filenames, phase, and iteration.

---

## Standards Handling

### Nature of Standards

- Standards are **session-scoped infrastructure**, not iterative workflow outputs.
- They are produced once per session.
- They must remain conceptually immutable for the session.

### StandardsProvider Interface

To support diverse standards strategies while maintaining clean boundaries:

```python
class StandardsProvider(ABC):
    @abstractmethod
    def create_bundle(self, context: dict[str, Any]) -> str:
        """Create standards bundle for the given context."""
        ...
```

### Engine Responsibilities

The engine:
1. Calls `profile.get_standards_provider()`
2. Calls `provider.create_bundle(context)`
3. Writes `standards-bundle.md`
4. Computes SHA256
5. Stores `standards_hash` in workflow state

```python
class WorkflowState(BaseModel):
    standards_hash: str  # SHA256 of standards-bundle.md
```

Standards are **not tracked as artifacts** and are not part of iteration logic.

---

## Approval System

### Step vs Approve Semantics

| Command                      | Responsibility                                    |
| ---------------------------- | ------------------------------------------------- |
| `aiwf step {session_id}`     | Perform deterministic engine work, advance phases |
| `aiwf approve {session_id}`  | Hash artifacts, set approval flags                |

**Step advances. Approve commits.**

### Approval Gates

| Phase     | Gate Condition                    | Approval Sets                     |
|-----------|-----------------------------------|-----------------------------------|
| PLANNED   | `plan_approved == True`           | `plan_approved`, `plan_hash`      |
| GENERATED | All artifacts have `sha256`       | `artifact.sha256` for each file   |
| REVIEWED  | `review_approved == True`         | `review_approved`, `review_hash`  |
| REVISED   | All artifacts have `sha256`       | `artifact.sha256` for each file   |

### ING Phase Approval

For ING phases (PLANNING, GENERATING, REVIEWING, REVISING), approval:
1. Reads prompt from disk (captures user edits)
2. Optionally hashes prompt (if `hash_prompts` enabled)
3. Calls provider with prompt content
4. Writes response if provider returns content

### ED Phase Approval

For ED phases (PLANNED, GENERATED, REVIEWED, REVISED), approval:
1. Reads output files from disk (captures user edits)
2. Computes and stores hashes
3. Sets approval flags

### Approval Command

```bash
aiwf approve {session_id}
aiwf approve {session_id} --hash-prompts
aiwf approve {session_id} --no-hash-prompts
```

---

## Hashing Strategy

### General Rules

- Hashing is performed **only on approval**.
- `write_artifacts()` writes files with `sha256=None`.
- The engine computes all hashes during `approve()`.
- Content is never stored in workflow state.
- Hash mismatches **do not block workflow** (non-enforcement).

### What Gets Hashed

| Approval Point | What Gets Hashed                     | Stored In                |
|----------------|--------------------------------------|--------------------------|
| PLANNED        | `plan.md`                            | `state.plan_hash`        |
| GENERATED      | `iteration-N/code/*` files           | `artifact.sha256`        |
| REVIEWED       | `iteration-N/review-response.md`     | `state.review_hash`      |
| REVISED        | `iteration-N/code/*` files           | `artifact.sha256`        |
| ING (optional) | `*-prompt.md`                        | `state.prompt_hashes`    |

### Prompt Hashing (Optional)

Controlled by:
- Config: `hash_prompts: false` (default)
- CLI: `--hash-prompts` / `--no-hash-prompts` (overrides config)

When enabled, prompts are hashed during ING approval and stored in `state.prompt_hashes` dict.

---

## WorkflowState Fields

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
    
    # State
    phase: WorkflowPhase
    status: WorkflowStatus
    execution_mode: ExecutionMode
    current_iteration: int = 1
    
    # Hashing and approval
    standards_hash: str
    plan_approved: bool = False
    plan_hash: str | None = None
    review_approved: bool = False
    review_hash: str | None = None
    prompt_hashes: dict[str, str] = {}
    
    # Providers
    providers: dict[str, str]  # role -> provider_key
    
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

## Configuration

### Location Precedence

1. `./.aiwf/config.yml` (project-specific, highest priority)
2. `~/.aiwf/config.yml` (user-specific)
3. Built-in defaults (fallback)

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

## Responsibility Boundaries (Strict)

### Profiles
- Parse AI responses
- Decide domain-specific policy
- Generate content strings
- Return WritePlan (what to write)
- Provide StandardsProvider
- **Never read or write files**
- **Never mutate workflow state**

### StandardsProvider
- Read standards sources (filesystem, DB, API, etc.)
- Assemble standards bundle
- **Never write to session directory**
- Return content as string

### Engine
- Owns all session file I/O
- Invokes StandardsProvider
- Writes all files and artifacts (with `sha256=None`)
- Executes WritePlan
- Computes all hashes (during `approve()`)
- Records approvals
- Advances workflow state

---

## Non-Enforcement Policy

This engine is **not adversarial**.

### File Editing Policy

- Editing files is allowed at any time
- The engine does not refuse to proceed due to file edits
- Hash mismatches log warnings but **never block workflow**

### Hashes Exist To

- Record what was approved (audit trail)
- Detect no-op revisions (UX improvement)
- Provide post-hoc visibility (debugging)

### What Hashes Do NOT Do

- Enforce immutability (not a goal)
- Block workflow progression (never happens)
- Prevent file modifications (developer freedom)

---

## WritePlan Contract

Profiles return WritePlan to specify what files to write:

```python
class WriteOp(BaseModel):
    path: str      # Relative path (e.g., "code/Tier.java")
    content: str   # File content

class WritePlan(BaseModel):
    writes: list[WriteOp] = []
```

**Engine executes WritePlan:**
- Prefixes paths with `iteration-{N}/`
- Creates parent directories
- Writes files
- Creates Artifact records with `sha256=None`
- Hashing deferred to `approve()`

**Profile never performs file I/O.**

---

## Out of Scope for M7

- Hash mismatch warnings (Slice 8 - deferred)
- Deduplication detection (Slice 8 - deferred)
- Multi-profile filename conventions
- Plugin systems beyond StandardsProvider
- UI / IDE integrations
- Distributed execution
- Security hardening
- Automated profile execution (approved=True workflows)
- Test generation (post-1.0 feature)

---

## Next Steps

Potential future work:
1. **Slice 8**: Hash mismatch warnings and deduplication detection
2. **README update**: Document current CLI and workflow
3. **ING/ED separation**: Refactor GENERATING/REVISING to pure ING behavior (optional cleanup)
4. **Consolidate hashes**: Move all hashes to single `hashes: dict[str, str]` field (tech debt)
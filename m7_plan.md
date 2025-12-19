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

## Core Workflow Model

### Phase Structure

The workflow consists of the following phases:

**WorkflowPhase Enum:**
```python
class WorkflowPhase(str, Enum):
    INITIALIZED = "initialized"
    
    # Planning
    PLANNING = "planning"      # *ING: prompt issued, awaiting response
    PLANNED = "planned"        # *ED: response received, processing
    
    # Generation
    GENERATING = "generating"  # *ING: prompt issued, awaiting response
    GENERATED = "generated"    # *ED: response received, code extracted
    
    # Review
    REVIEWING = "reviewing"    # *ING: prompt issued, awaiting response
    REVIEWED = "reviewed"      # *ED: response received, verdict processed
    
    # Revision
    REVISING = "revising"      # *ING: prompt issued, awaiting response
    REVISED = "revised"        # *ED: response received, code extracted
    
    # Terminal
    COMPLETE = "complete"
```

### Phase Responsibility Split

***ING* phases:**
- Prompt issuance
- File existence gating
- Waiting for user to provide response file
- No hashing occurs

***ED* phases:**
- Response processing
- Artifact extraction
- State transition decisions
- No hashing occurs (happens on approval)

This split is documented in ADR-0001 (as amended) and enforced by tests.

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
├── standards-bundle.md      # Created at init, immutable
└── planning-response.md     # Created in PLANNING, immutable after approval
```

**Iteration-Scoped Files:**
```
.aiwf/sessions/{session-id}/
├── iteration-1/
│   ├── generating-prompt.md
│   ├── generating-response.md
│   ├── code/
│   │   ├── Tier.java
│   │   └── TierRepository.java
│   ├── reviewing-prompt.md
│   └── reviewing-response.md
│
└── iteration-2/              # Created only if revision needed
    ├── revising-prompt.md
    ├── revising-response.md
    ├── code/
    │   ├── Tier.java         # Revised
    │   └── TierRepository.java
    ├── reviewing-prompt.md
    └── reviewing-response.md
```

**Note:** Planning prompt/response are session-scoped (not in iteration directories).

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
    phase: WorkflowPhase      # GENERATED, REVISED
    iteration: int            # 1, 2, 3, ...
    sha256: str | None        # File hash for deduplication
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

**Interface definition:**
```python
class StandardsProvider(ABC):
    """
    Provides standards content for a workflow session.
    
    This is the ONLY component allowed to perform I/O for standards.
    Profiles provide a provider; engine invokes it.
    """
    
    @abstractmethod
    def create_bundle(self, context: dict[str, Any]) -> str:
        """
        Create standards bundle for the given context.
        
        Args:
            context: Workflow context (scope, entity, etc.)
            
        Returns:
            Complete standards bundle as string
            
        May perform I/O (filesystem, DB, API, etc.)
        """
        ...
    
    @abstractmethod
    def read_bundle(self, session_dir: Path) -> str:
        """
        Read standards bundle from session directory.
        
        Args:
            session_dir: Path to session directory
            
        Returns:
            Standards bundle content
            
        Used for verification (hash checking)
        """
        ...
```

### Profile Registration

**Profiles provide standards provider:**
```python
class WorkflowProfile(ABC):
    @abstractmethod
    def get_standards_provider(self) -> StandardsProvider:
        """Return the standards provider for this profile."""
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

### Boundary Rules

- **Profile**: Zero I/O (provides provider)
- **Provider**: I/O allowed (adapter pattern)
- **Engine**: Invokes provider, writes bundle, computes hash

### Implementation Examples

**FileBasedStandardsProvider (jpa-mt):**
- Reads markdown files from filesystem
- Merges based on layer-to-standards mapping
- Concatenates with separators

**Future providers:**
- RagStandardsProvider: Queries vector database
- ApiStandardsProvider: Fetches from REST API
- DatabaseStandardsProvider: Queries relational database

### Standards Verification (Non-Blocking)

Engine checks standards hash on approval:

```python
def check_standards_unchanged(
    provider: StandardsProvider,
    session_dir: Path,
    expected_hash: str
) -> bool:
    """
    Check if standards have changed.
    
    Returns:
        True if unchanged, False if changed
        
    Does NOT raise exception.
    Logs warning if mismatch.
    Does NOT block workflow.
    """
    try:
        current_bundle = provider.read_bundle(session_dir)
        current_hash = hashlib.sha256(current_bundle.encode()).hexdigest()
        
        if current_hash != expected_hash:
            logger.warning(
                "⚠️  Standards bundle has changed since session creation. "
                "This may affect workflow consistency."
            )
            return False
        
        return True
    
    except Exception as e:
        logger.warning(f"Could not verify standards: {e}")
        return False
```

**Verification behavior:**
- If unchanged: Continue silently
- If changed: Log warning, continue anyway
- Hash mismatches **DO NOT** block workflow
- Used for audit trail and user awareness only

---

## Planning Semantics

### Editable Until Approval

- During **PLANNING**, `planning-response.md` may be edited by the developer.
- Planning is reviewed manually.

### Plan Approval

Planning is approved explicitly by the developer via:

```bash
aiwf approve
```

**Note:** No phase argument required. Engine knows current phase.

### Approval Process

When `aiwf approve` is issued during PLANNING → GENERATED transition:

1. Developer reviews `planning-response.md`
2. Developer runs: `aiwf approve`
3. Profile validates planning response (profile-specific logic)
4. If valid, profile returns `ProcessingResult(approved=True)`
5. Engine computes `plan_hash` from `planning-response.md`
6. Engine sets `plan_approved=True`
7. Engine transitions to GENERATING

How approval validation works is profile-specific.
The engine only enforces that approval occurred via state transition.

### After Approval

- Planning becomes immutable (conceptually).
- Engine computes and stores `plan_hash`.
- Any change after approval is logged but does not block workflow.

```python
class WorkflowState(BaseModel):
    plan_approved: bool
    plan_hash: str | None  # SHA256 of planning-response.md
```

If the plan must change after approval, a **new session is required**.

---

## Step vs Approve Semantics

### Core Distinction

| Command        | Responsibility                                         |
| -------------- | ------------------------------------------------------ |
| `aiwf step`    | Perform deterministic engine work and advance workflow |
| `aiwf approve` | Commit current artifacts and compute/store hashes      |

**Step advances. Approve commits.**

### Why Approval Exists

Approval is required for **technical correctness**, not UX preference.

Approval:
1. Defines the **hash boundary**
2. Ensures hashes reflect **what the developer accepted**
3. Enables **no-op revision detection**
4. Supports both **human-in-the-loop** and **automated profiles**

Hashing during `step` is explicitly rejected because files may still be edited.

### Approval Command

**No phase argument required:**
```bash
aiwf approve
```

The engine always knows the current phase; therefore approval applies to the current approval boundary in engine state.

---

## Explicit Approvals

Approvals are **explicit, user-driven checkpoints**.

### Semantics of Approval

When `aiwf approve` is issued, the engine:

1. Verifies required files for the phase exist
2. Computes SHA256 hashes for those files
3. Records hashes and approval metadata in state

Approval:
- **does not lock the filesystem**
- **does not prevent edits**
- serves as an **audit and comparison point only**
- **does not block workflow on hash mismatches**

---

## ProcessingResult Contract

### Updated Structure

```python
class ProcessingResult(BaseModel):
    status: WorkflowStatus          # SUCCESS, ERROR, IN_PROGRESS
    approved: bool = False          # True if no human review needed
    write_plan: WritePlan | None = None
    artifacts: list[Artifact] = []
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### approved Flag Semantics

**`approved=True`:**
- Profile completed all required checks
- No human review required
- Engine may proceed to next phase after `aiwf approve`

**`approved=False` (default for M7):**
- Engine must wait for `aiwf approve` before advancing
- Human review required

### Policy for M7

**Policy A:**
- One workflow transition per `step`
- Even if `approved=True`, engine does not auto-step again
- Explicit `aiwf approve` always required

The flag exists to:
- Reduce UX friction where possible (future)
- Support future automated profiles
- Make approval state explicit

### WorkflowStatus Clarification

`WorkflowStatus` describes **what happened**, not approval state:

- `SUCCESS` → processing completed correctly
- `ERROR` → invalid input / unrecoverable error
- `IN_PROGRESS` → awaiting external input (missing response file)

**Constraint:**
- `IN_PROGRESS` must **only** mean "waiting for input"
- Approval is **never inferred** from `WorkflowStatus`

---

## ING / ED Execution Model

### ING (Prompt Creation)

- `step` executes ING logic
- Engine writes prompt file
- Profile may iterate internally (automated) or require human review (`approved=False`)
- **No hashing occurs**

### ED (Response Processing)

- `step` executes ED logic
- Engine processes response via profile
- For generation/revision: code files are extracted
- Developer may edit extracted code
- **No hashing occurs** (happens on approval)

### Approval

- `aiwf approve` hashes the **final accepted state**
- Hashes reflect post-edit prompt/response and post-edit code files
- Hashes used for audit and deduplication only
- Hash mismatches log warnings but **do not block workflow**

---

## Hashing Strategy

### General Rules

- Hashing is performed **only on approval**.
- The engine computes all hashes.
- Content is never stored in workflow state.
- Hash mismatches **do not block workflow** (non-enforcement).

### What Gets Hashed

#### Plan Approval
- `planning-prompt.md` (optional)
- `planning-response.md` (required)
- `standards-bundle.md` (checked, not hashed again if already hashed at init)

#### Generation / Revision Approval
- All files under `iteration-N/code/*` (per-file hashes)
- `generating-response.md` or `revising-response.md` (optional, audit only)

#### Review Approval
- `reviewing-prompt.md` (optional)
- `reviewing-response.md` (optional)

### Deduplication Algorithm

Dedup applies **only to code outputs**.

**Per-file hash comparison between iterations:**

```python
def is_identical_to_previous_iteration(
    current_iter: int, 
    artifacts: list[Artifact]
) -> bool:
    """
    Compare code artifacts between iteration N and N-1.
    
    Returns True if all files are identical (same names, same hashes).
    """
    
    # Get code artifacts for both iterations
    prev_files = {
        a.path.split('/')[-1]: a.sha256  # filename -> hash
        for a in artifacts
        if a.iteration == current_iter - 1 and '/code/' in a.path
    }
    
    curr_files = {
        a.path.split('/')[-1]: a.sha256
        for a in artifacts
        if a.iteration == current_iter and '/code/' in a.path
    }
    
    # File count must match
    if len(prev_files) != len(curr_files):
        return False
    
    # All filenames must match
    if set(prev_files.keys()) != set(curr_files.keys()):
        return False
    
    # All hashes must match
    for filename in prev_files:
        if prev_files[filename] != curr_files[filename]:
            return False
    
    return True
```

**When identical code detected:**
1. Log warning: `"⚠️  Revision produced no changes"`
2. Provide user feedback about potential causes
3. Optionally skip automatic review (implementation decision)
4. Prompt user for next action

**Edge cases:**
- **Different file count:** NOT identical (file added/removed)
- **Different filenames:** NOT identical (rename counts as change)
- **Same filename, different hash:** NOT identical (content changed)

### No Directory-Level Hashing

All hashing is per-file. No aggregate directory hashes are computed or stored.

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
- Writes all files and artifacts
- Executes WritePlan
- Computes all hashes
- Records approvals
- Advances workflow state
- Performs hash verification (non-blocking)

---

## Non-Enforcement Policy

This engine is **not adversarial**.

### File Editing Policy

- Editing past files is allowed at any time
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
- Lock filesystem state (not possible)

### Hash Verification Behavior

**Standards hash mismatch:**
- Log: `"⚠️  Standards changed since session creation"`
- Continue workflow
- User awareness only

**Plan hash mismatch:**
- Log: `"⚠️  Plan changed since approval"`
- Continue workflow
- User awareness only

**Code hash mismatch:**
- Log: `"⚠️  Code changed since approval"`
- May affect deduplication detection
- Continue workflow

**Rationale:**
- Trust the developer
- Hashes are for audit, not enforcement
- Workflow correctness based on **current inputs**
- No adversarial blocking

Correctness depends on **current phase inputs and current iteration outputs**, not on historical files.

---

## WritePlan Contract

Profiles return WritePlan to specify what files to write:

```python
class WriteOp(BaseModel):
    path: str      # Relative to session root
    content: str   # File content

class WritePlan(BaseModel):
    writes: list[WriteOp] = []
```

**Engine executes WritePlan:**
- Creates parent directories
- Writes files
- Computes SHA256 per file
- Returns Artifact metadata with hashes

**Profile never performs file I/O.**

---

## Configuration Architecture

### Engine Configuration

**Location precedence:**
1. `./.aiwf/config.yml` (project-specific, highest priority)
2. `~/.aiwf/config.yml` (user-specific)
3. Built-in defaults (fallback)

**Structure:**
```yaml
# Engine configuration
working_directory: ".aiwf"
standards_root: "${STANDARDS_DIR}"  # Default for all profiles
default_profile: "jpa-mt"
```

### Profile Configuration

**Location:** `profiles/jpa-mt/config.yml` (packaged with profile)

**Structure:**
```yaml
# Domain policy (profile-specific)
scopes:
  domain:
    layers: [entity, repository]
  vertical:
    layers: [entity, repository, service, controller, dto, mapper]

layer_standards:
  _universal:
    - PACKAGES_AND_LAYERS.md
    - NAMING_AND_API.md
  entity:
    - ORG.md
    - JPA_AND_DATABASE.md
    - ARCHITECTURE_AND_MULTITENANCY.md
  repository:
    - ORG.md
    - JPA_AND_DATABASE.md
  # etc.

# Optional: Override engine defaults
# standards_root: "/custom/jpa/standards"
```

---

## Out of Scope for M7

- ADR formalization
- Multi-profile filename conventions
- Plugin systems beyond StandardsProvider
- UI / IDE integrations
- Distributed execution
- Security hardening
- Automated profile execution (approved=True workflows)
- Test generation (post-1.0 feature)

---

## Execution Strategy

### Slice Discipline

Work proceeds in discrete slices.
Each slice must:
- obey this plan,
- avoid speculative abstraction,
- minimize scope.

If drift occurs:
- stop,
- return to this document,
- realign.

---

## Status

This plan supersedes all prior guidance.
Approved by project owner.
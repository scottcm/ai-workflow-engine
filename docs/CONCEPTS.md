# Core Concepts

Deep dive into the AI Workflow Engine's components and design philosophy.

---

## Table of Contents

- [The Three-Component Model](#the-three-component-model)
- [The Engine](#the-engine)
- [Profiles](#profiles)
- [AI Providers](#ai-providers)
- [Approval Providers](#approval-providers)
- [Standards Providers](#standards-providers)
- [Phase + Stage Workflow Model](#phase--stage-workflow-model)
- [Approval Gate Semantics](#approval-gate-semantics)
- [Deferred Hashing Strategy](#deferred-hashing-strategy)
- [Convention-Based Boundaries](#convention-based-boundaries)

---

## The Three-Component Model

The engine separates three orthogonal concerns:

```
┌─────────────────────────────────────────────┐
│  WHAT to generate (Profile)                │
│  ↓                                          │
│  HOW to access AI (AI Provider)            │
│  ↓                                          │
│  WHEN to advance (Approval Provider)        │
└─────────────────────────────────────────────┘
```

**Example combinations:**

| Profile | AI Provider | Approval Provider | Use Case |
|---------|-------------|------------------|----------|
| jpa-mt | manual | manual | Budget-friendly, full control |
| jpa-mt | claude-code | claude-code | Fully automated with AI gates |
| jpa-mt | manual | skip | Fast iteration, no gates |
| react-ts | gemini-cli | manual | Different stack, automated generation |

This separation enables:
- Reusing profiles across AI providers
- Reusing AI providers across profiles
- Mixing automated and manual workflows
- Testing without real AI or filesystem

---

## The Engine

The **AI Workflow Engine** (aiwf) orchestrates workflow state and file management. It is completely agnostic to:
- Which AI you use (ChatGPT, Claude, Gemini, etc.)
- What language/technology you're generating (Java, Python, TypeScript, etc.)
- How AI is accessed (web chat, CLI agent, API)

### Engine Responsibilities

**Orchestration:**
- Advance workflow through phases and stages
- Execute TransitionTable state machine
- Manage approval gates
- Track iterations

**File I/O:**
- Execute profile WritePlans (read/write files)
- Write prompt files
- Read response files
- Manage session state persistence

**State Management:**
- Persist WorkflowState to session.json
- Track hashes for audit trail
- Manage artifact metadata
- Record messages and errors

**Validation:**
- Path traversal prevention
- Project root enforcement
- Provider configuration validation
- Input sanitization

### What the Engine Does NOT Do

- Generate prompts (profiles do this)
- Parse AI responses (profiles do this)
- Call AI directly (providers do this)
- Make approval decisions (approval providers do this)

---

## Profiles

**Profiles** implement domain-specific generation logic. A profile knows:
- How to structure prompts for a specific domain
- What standards apply (coding conventions, patterns)
- How to parse AI responses and extract code
- What file structure to create

### Profile Interface

```python
class WorkflowProfile(ABC):
    @abstractmethod
    def generate_plan_prompt(self, context: dict) -> str:
        """Generate planning phase prompt."""

    @abstractmethod
    def process_plan_response(self, content: str, context: dict) -> ProcessingResult:
        """Parse plan response, return WritePlan."""

    @abstractmethod
    def generate_generate_prompt(self, context: dict) -> str:
        """Generate code generation prompt."""

    @abstractmethod
    def process_generate_response(self, content: str, ...) -> ProcessingResult:
        """Extract code, return WritePlan."""

    # Similar for review and revise phases...
```

### Profile Responsibilities

**Input Processing:**
- Accept workflow context (session info, user inputs)
- Load standards and templates
- Compose prompts with placeholders filled

**Output Processing:**
- Parse AI responses (markdown, code blocks, metadata)
- Extract code and metadata
- Return WritePlan (what files to create/update)

**What Profiles Return:**
- Prompts (strings)
- ProcessingResult with WritePlan
- Never modify files directly

### Profile Constraints

Profiles are **pure functions** of context → output:
- No file I/O (return WritePlan instead)
- No state mutation (return new state)
- Deterministic (same inputs → same outputs)
- Testable without filesystem

**Why these constraints?**
- Testability: Mock context, verify output
- Reusability: Profiles work with any engine version
- Clarity: Side effects handled by engine, not scattered

---

## AI Providers

**AI Providers** abstract how AI is accessed. They handle prompt delivery and response retrieval.

### Provider Types

**Manual Provider:**
- Creates response file (empty)
- Returns `None` (signals user will provide content)
- Budget-friendly, works with free AI web interfaces

**CLI Providers** (claude-code, gemini-cli):
- Execute CLI command with prompt
- Return `AIProviderResult` with file content
- `fs_ability="local-write"` - can write files directly

**API Providers** (future):
- Call AI API with prompt
- Return `AIProviderResult` with content string
- `fs_ability="none"` - engine writes files

### Provider Interface

```python
class AIProvider(ABC):
    @abstractmethod
    def validate(self) -> None:
        """Verify provider is configured and accessible."""

    @abstractmethod
    def generate(self, prompt: str, context: dict | None = None) -> AIProviderResult | None:
        """Generate response. Returns None for manual mode."""
```

### fs_ability Metadata

Providers declare file system capability:

| fs_ability | Meaning | Example |
|------------|---------|---------|
| `local-write` | Can read/write project files | claude-code, gemini-cli |
| `local-read` | Can read but not write files | Future: RAG-enabled approver |
| `none` | No filesystem access | Future: API-only providers |

Engine uses `fs_ability` to:
- Generate appropriate output instructions in prompts
- Determine whether to write files or trust provider
- Pass `None` or content in file dicts to approvers

---

## Approval Providers

**Approval Providers** evaluate content at workflow gates and return APPROVED, REJECTED, or PENDING decisions.

### What Approval Gates Check

Approval gates are **quality checkpoints** asking "is this ready to proceed?" They check fitness for purpose, not technical correctness:

**PROMPT stages:** "Is this prompt clear and complete enough to get good results?"
- Has all required context
- Clear instructions
- No template errors

**RESPONSE stages:** "Did the AI answer what was asked?"
- Well-formatted output
- Followed instructions
- Addressed the requirements

**What gates are NOT:**
- Not code review (that's the REVIEW phase content)
- Not validation of technical correctness
- Not enforcement of coding standards

### Example: REVIEW[RESPONSE] Gate

The gate evaluates **the review document itself** (review-response.md):

**Checks:**
- ✅ Well-formatted, follows expected structure
- ✅ Actionable feedback (specific line numbers, concrete suggestions)
- ✅ Aligned with coding standards
- ✅ Complete (addresses all aspects)
- ✅ Findings are valid (not false positives)

**Can reject with feedback:**
- "Too vague - says 'improve error handling' without specifics"
- "Doesn't cite which standards rules are violated"
- "Flagged @Transactional as wrong but it's correct per Spring docs"

On rejection, the provider **regenerates the review** using feedback as guidance.

### Built-in Approval Providers

**SkipApprovalProvider:**
- Always returns APPROVED
- Use for stages where no gate is needed
- Enables fast iteration

**ManualApprovalProvider:**
- Returns PENDING
- Workflow pauses for user decision
- User runs `approve` or `reject` command

**AIApprovalProvider (adapter):**
- Delegates to any AI provider
- Returns APPROVED or REJECTED with feedback
- Supports auto-retry on rejection

### Approval vs Review: The Distinction

| Aspect | Approval Gate | REVIEW Phase |
|--------|---------------|--------------|
| **What** | Process artifacts | Code quality |
| **Checks** | Artifact fitness | Technical correctness |
| **Scope** | Single file quality | Full codebase review |
| **Output** | APPROVED/REJECTED | review-response.md |

**GENERATE[RESPONSE] approval gate:**
- ❌ Does NOT ask: "Is this code well-designed?" (that's REVIEW)
- ✅ Does ask: "Did the AI follow the plan?" (completeness check)

**REVIEW[RESPONSE] approval gate:**
- ❌ Does NOT ask: "Is the code good?" (the review already did that)
- ✅ Does ask: "Is the review itself useful?" (quality of review)

**Technical note:** Approvers with filesystem access can read any session file, not just what the engine explicitly passes. The separation between "review of review" and "code review" is enforced through prompt engineering and convention, not technical restrictions.

---

## Standards Providers

**Standards Providers** retrieve coding standards for a profile. They implement different retrieval strategies.

### Provider Types

**BundleStandardsProvider:**
- Loads pre-assembled markdown bundle
- Fast, deterministic
- Current default for jpa-mt

**FileSystemStandardsProvider:**
- Aggregates standards from multiple files
- Supports glob patterns
- Useful for large standard sets

**Future providers:**
- RAG-based (semantic search over standards)
- API-based (fetch from remote source)
- Git-based (load from specific commit/branch)

### Why Separate Standards Providers?

- Profiles declare "I need standards" without knowing retrieval strategy
- Standards sources can evolve (file → database → RAG) without profile changes
- Testing profiles with mock standards

---

## Phase + Stage Workflow Model

### Phase Overview

Workflow progresses through 8 phases:

```
INIT → PLAN → GENERATE → REVIEW → REVISE → COMPLETE
                                    ↓
                                  ERROR
                                    ↓
                                CANCELLED
```

**Active phases** (PLAN, GENERATE, REVIEW, REVISE) have two stages each:
- **PROMPT stage:** Profile creates prompt, awaits approval
- **RESPONSE stage:** AI produces response, awaits approval

**Terminal phases** (INIT, COMPLETE, ERROR, CANCELLED) have no stages.

### Stage Flow

```
PHASE[PROMPT] ──approve──► PHASE[RESPONSE] ──approve──► NEXT_PHASE[PROMPT]
      │                          │
      └── prompt editable        └── AI called, response editable
```

**Work happens AFTER entering each stage:**
- Enter PROMPT → profile creates prompt → user can edit → approve
- Enter RESPONSE → AI produces response → user can edit → approve

### TransitionTable State Machine

The `TransitionTable` is a declarative state machine mapping (phase, stage, command) → transition:

```python
(PLAN, PROMPT, "approve") → Transition(
    next_phase=PLAN,
    next_stage=RESPONSE,
    action=CALL_AI,
)

(PLAN, RESPONSE, "approve") → Transition(
    next_phase=GENERATE,
    next_stage=PROMPT,
    action=CREATE_PROMPT,
)
```

Each transition specifies:
- Next phase and stage
- Action to execute (CREATE_PROMPT, CALL_AI, EXTRACT_CODE, etc.)
- Validation rules

**Benefits:**
- Testable: Pure data structure
- Auditable: Clear transition log
- Extensible: Add transitions without modifying logic

---

## Approval Gate Timing

Approval gates run **immediately after content creation**, not when user issues `approve` command.

**Flow:**
1. Content created (prompt or response)
2. Gate runs automatically
3. If APPROVED: continue
4. If REJECTED: handle rejection (retry, suggested_content, halt)
5. If PENDING: pause for user input (`approve`/`reject` command)
6. User's `approve` command resolves PENDING state, workflow continues

**Why this design?**
- Eliminates `isinstance` checks for ManualApprovalProvider
- All providers treated uniformly (all return ApprovalResult)
- Enables fully automated workflows (all approvers are `skip` or AI-based)

**Rejection handling:**
- `retry_count` tracks auto-retry attempts
- `approval_feedback` stored for regeneration guidance
- `suggested_content` can hint at fixes
- After `max_retries`, workflow pauses (not ERROR)

---

## Deferred Hashing Strategy

The engine computes hashes **after approval gates**, not before.

### Why Defer Hashing?

**User edit window:**
- User can edit prompts before approval
- User can edit responses before approval
- Hash captures final content, including user edits

**Approval gate rationale:**
- Gates may reject and request regeneration
- No point hashing content that will be replaced
- Hash represents "what was actually approved"

### Hash Timing

```
1. Create content (prompt or response)
2. Run approval gate
   - If REJECTED: regenerate, goto 1
   - If PENDING: wait for user input
3. User approves
4. Compute hash NOW
5. Advance to next stage
```

**Non-enforcement policy:**
- Hash mismatches log warnings
- Workflow never blocked by hash mismatch
- Hashes for audit trail, not enforcement

---

## Convention-Based Boundaries

Component boundaries are **design conventions**, not technical restrictions. The architecture relies on components honoring their contracts.

### I/O Responsibility

**By convention:**
- Profiles delegate I/O to engine via WritePlan
- Some providers do their own I/O based on `fs_ability`

**By enforcement:**
- Nothing. No sandbox, no restrictions.

**Why this approach?**
- **Simplicity:** No sandbox complexity, no permission systems
- **Trust:** Components are part of the same system
- **Extensibility:** Profiles/providers can use filesystem if needed
- **Testability:** Tests can still verify WritePlans without I/O

### Technical Note for Documentation

When documenting, balance simplicity with accuracy:

**Lead with the mental model:**
> Profiles delegate I/O to the engine via WritePlan. Providers may read/write files directly based on their `fs_ability`.

**Add technical note:**
> *These boundaries are design conventions, not enforced restrictions. The architecture relies on components honoring their contracts. The convention-based approach prioritizes simplicity and extensibility over enforcement.*

This acknowledges reality while explaining the deliberate design choice.

---

## Summary

The AI Workflow Engine succeeds through clear separation of concerns:

- **Engine** orchestrates state and I/O
- **Profiles** generate prompts and parse responses
- **AI Providers** abstract AI access methods
- **Approval Providers** enforce quality gates
- **Standards Providers** supply domain knowledge

Convention-based boundaries, explicit state machines, and deferred hashing create a system that's:
- Testable without mocking
- Extensible without core changes
- Transparent through file materialization
- Auditable through complete trails
- Flexible across AI providers and budgets
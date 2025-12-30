# AI Workflow Engine

**Enterprise-grade workflow orchestrator for AI-assisted code generation**

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Production Status:** v0.9.0 - Core workflow complete, extended CLI commands planned for 1.0.0

A stateful, resumable workflow engine that orchestrates multi-phase AI-assisted code generation with explicit approval gates, artifact tracking, and iteration management. Built to demonstrate enterprise architecture patterns while solving real-world development challenges.

**Key Features:**
- 📋 Multi-phase workflow: Planning → Generation → Review → Revision
- ✅ Explicit approval gates with deferred hashing  
- 🔄 Iteration tracking with complete audit trail
- 🎯 Profile-based extensibility (language/framework agnostic)
- 🔐 Security-conscious path validation and isolation
- 💾 File-materialized semantics (every output is editable)
- 💰 **Budget-friendly:** Works with free AI web interfaces, not expensive APIs
- 🎛️ **Full control:** Manual mode lets you edit prompts and review responses

---

## Table of Contents

- [Background](#background)
- [Quick Start](#quick-start)
- [What This Project Demonstrates](#what-this-project-demonstrates)
- [Architecture Overview](#architecture-overview)
- [CLI Reference](#cli-reference)
- [Workflow Tutorial](#workflow-tutorial)
- [Configuration](#configuration)
- [JPA Multi-Tenant Profile](#jpa-multi-tenant-profile)
- [Extending the Engine](#extending-the-engine)
- [Documentation](#documentation)
- [Development Setup](#development-setup)
- [Known Limitations](#known-limitations)
- [Project Status](#project-status)
- [License](#license)

---

## Background

This project originated from production needs at Skills Harbor, a startup building multi-tenant SaaS applications. Like many startups, Skills Harbor operates with limited budgets and needed a way to leverage AI for code generation without expensive API subscriptions.

The solution: a workflow engine that works with consumer AI subscriptions (ChatGPT web interface, Claude.ai, Gemini) and CLI agents—not enterprise API keys. This "manual mode" approach provides budget-friendly access to cutting-edge AI while maintaining full control over prompts and responses.

Skills Harbor is predominantly a Java shop, which drove the creation of the `jpa-mt` profile for JPA/Spring Data generation. However, the engine architecture is deliberately language-agnostic—profiles can be created for any technology stack.

**Why This Approach?**
- **Budget reality**: Works with free/low-cost AI subscriptions and manual workflows
- **Real-world complexity**: Built to support actual multi-tenant SaaS patterns (JPA, RLS, Spring Data)
- **Auditability**: Every prompt, response, and iteration preserved as editable files
- **Extensibility**: New languages/frameworks added via profiles, not core modifications
- **Developer control**: Edit prompts before submission, review responses before processing

Built as an independent project with permission, this engine demonstrates enterprise architecture patterns while solving real development workflow challenges.

---

## Key Concepts

Understanding how the engine works requires understanding three distinct components:

### 1. The Engine (AI & Language Agnostic)

The **AI Workflow Engine** (aiwf) orchestrates the workflow of planning → generating → reviewing → revising code. It is completely agnostic to:
- **Which AI** you use (ChatGPT, Claude, Gemini, etc.)
- **What language/technology** you're generating (Java, Python, TypeScript, etc.)
- **How AI is accessed** (web chat, CLI agent, API)

The engine's job is workflow management:
- Track workflow state (phases, iterations, approvals)
- Generate prompts at the right time
- Process responses when available
- Manage artifacts and file I/O
- Enforce approval gates
- Persist session state

**The engine never generates prompts or processes code directly**—that's the profile's job.

---

### 2. Profiles (Language & Technology Specifics)

**Profiles** are extensions that implement language/technology-specific generation logic. A profile knows:
- How to structure prompts for a specific domain (e.g., JPA entity generation)
- What standards apply (coding conventions, architectural patterns)
- How to parse AI responses and extract code
- What file structure to create

**How they work** is largely up to the implementor, but the design pattern is:
- **Input:** Workflow context (entity name, table, scope, etc.)
- **Output:** Prompts (strings) or WritePlans (what files to create)
- **Constraints:** Never perform file I/O, never mutate workflow state

**Current profile:**
- `jpa-mt` - Produces Java/JPA/Spring Data code for multi-tenant databases

**The architecture supports any technology:**
- React/TypeScript frontend components
- Python/FastAPI backend services  
- Go microservices
- Ruby on Rails models
- Any language or framework

Creating a new profile means implementing the `WorkflowProfile` interface and registering it with the engine. The engine handles everything else.

---

### 3. AI Providers (How AI is Accessed)

**AI Providers** are extensions that handle the mechanics of getting prompts to AI and responses back. They abstract away:
- API calls vs CLI agents vs web interfaces
- Authentication and configuration
- Response streaming and parsing

**Current provider:**
- `manual` - Human-in-the-loop mode

**How `manual` provider works:**
1. Engine writes prompt to `.md` file (e.g., `planning-prompt.md`)
2. **You** copy prompt content to your AI of choice (ChatGPT, Claude, Gemini, etc.)
3. **You** copy AI response and save it to response file (e.g., `planning-response.md`)
4. Engine processes response file when you run `aiwf step`

This approach:
- Works with **free AI web interfaces** (ChatGPT.com, Claude.ai, Gemini)
- Works with **CLI agents** (Claude Desktop, Gemini CLI)
- Gives you **full control** over prompt editing before submission
- Provides complete **audit trail** (all prompts/responses saved as files)
- **No API costs** - use whatever AI subscription you already have

**Future providers** (planned):
- `claude-cli` - Automated via Claude Desktop agent
- `gemini-cli` - Automated via Gemini CLI agent
- `openai-api` - Automated via OpenAI API

---

### 4. Standards Providers (How Coding Standards are Retrieved)

**Standards Providers** are profile-specific extensions that retrieve and bundle coding standards for a session. They answer the question: "What coding rules should AI follow?"

**Why this matters:** During `aiwf init`, the engine calls the profile's standards provider to create a `standards-bundle.md` file. This bundle contains all the coding conventions, architectural patterns, and best practices that AI should follow when generating code. The bundle is **created once per session and never changes** - ensuring consistency across all phases.

**The StandardsProvider interface:**
```python
class StandardsProvider(Protocol):
    def create_bundle(self, context: dict[str, Any]) -> str:
        """
        Create standards bundle for the given context.
        
        Args:
            context: Workflow context (scope, entity, bounded_context, etc.)
            
        Returns:
            Complete standards bundle as a string (markdown)
        """
        ...
```

**How it works:**
1. During `aiwf init`, engine asks profile for its standards provider
2. Profile returns a `StandardsProvider` instance
3. Engine calls `provider.create_bundle(context)` with workflow context
4. Provider returns complete standards text
5. Engine writes `standards-bundle.md` and computes its hash
6. Bundle is included in every prompt throughout the session

**Different retrieval strategies:**

Profiles can implement standards retrieval however they need:

**File-based (jpa-mt approach):**
```python
class JpaMtStandardsProvider:
    def __init__(self, config):
        self.standards_root = Path(config['standards']['root'])
        self.scopes = config['scopes']
        self.layer_standards = config['layer_standards']
    
    def create_bundle(self, context: dict[str, Any]) -> str:
        scope = context.get('scope')
        layers = self.scopes[scope]['layers']
        
        # Read files based on scope-specific layers
        # e.g., domain scope → entity + repository standards
        # vertical scope → entity + repository + service + controller
        
        files = self._select_files_for_layers(layers)
        return self._concatenate_files(files)
```

**RAG-based (hypothetical):**
```python
class RagStandardsProvider:
    def __init__(self, config):
        self.vector_db = VectorDatabase(config['db_url'])
    
    def create_bundle(self, context: dict[str, Any]) -> str:
        # Query vector database for relevant standards
        entity = context.get('entity')
        scope = context.get('scope')
        
        query = f"coding standards for {scope} scope {entity} entity"
        results = self.vector_db.similarity_search(query, k=10)
        
        return self._format_standards(results)
```

**API-based (hypothetical):**
```python
class ApiStandardsProvider:
    def __init__(self, config):
        self.api_client = StandardsApiClient(config['api_key'])
    
    def create_bundle(self, context: dict[str, Any]) -> str:
        # Fetch standards from central API
        bounded_context = context.get('bounded_context')
        scope = context.get('scope')
        
        response = self.api_client.get_standards(
            context=bounded_context,
            scope=scope
        )
        
        return response.markdown_content
```

**Git-based (hypothetical):**
```python
class GitStandardsProvider:
    def __init__(self, config):
        self.repo = GitRepo(config['repo_url'])
    
    def create_bundle(self, context: dict[str, Any]) -> str:
        # Clone/pull standards repository
        # Select files based on context
        # Return concatenated content
        ...
```

**Key benefits:**
- **Flexibility:** Profiles control how standards are retrieved
- **Centralization:** Standards can come from any source (files, DB, API, git)
- **Scope-awareness:** Different scopes get different standards (jpa-mt example)
- **Immutability:** Bundle created once, never changes during session
- **Auditability:** `standards-bundle.md` shows exactly what AI was told

**The jpa-mt file-based approach:**

The jpa-mt profile uses a layered, scope-aware file system:

```yaml
# profiles/jpa_mt/config.yml
scopes:
  domain:
    layers: [entity, repository]
  vertical:
    layers: [entity, repository, service, controller]

layer_standards:
  _universal: [CORE_CONVENTIONS.md]
  entity: [JPA_ENTITY.md, MULTI_TENANT.md]
  repository: [JPA_REPOSITORY.md]
  service: [SERVICE_LAYER.md]
  controller: [REST_CONTROLLER.md]
```

For a **domain scope** session:
- Loads: `_universal` + `entity` + `repository` standards
- Result: ~3 files concatenated into bundle

For a **vertical scope** session:
- Loads: `_universal` + `entity` + `repository` + `service` + `controller` standards
- Result: ~5 files concatenated into bundle

This ensures AI only gets relevant standards for the code being generated.

---

### 5. Execution Mode vs Providers (Orthogonal Concerns)

The workflow engine separates two independent concerns:

| Concern | Question Answered | Options |
|---------|-------------------|---------|
| **Execution Mode** | Who drives the workflow? | `INTERACTIVE` (user), `AUTOMATED` (engine) |
| **Providers** | Who produces responses? | `manual`, `claude`, `gemini`, etc. |

**Execution Mode (Control Flow):**
- `INTERACTIVE`: User must issue `step` and `approve` commands to advance the workflow
- `AUTOMATED`: Engine advances automatically without user commands

**Providers (Data Flow):**
- `manual`: No programmatic response; expects response file written externally (by user or AI agent)
- `claude`/`gemini`/etc.: API call produces the response automatically

**Key Insight:** These are orthogonal. You can mix and match:

| Mode | Providers | Use Case |
|------|-----------|----------|
| INTERACTIVE + all manual | User copies prompts to AI chat, pastes responses, runs step/approve | Budget-friendly, full control |
| INTERACTIVE + claude | User controls *when* to advance, Claude produces *what* | Human-paced with API automation |
| AUTOMATED + all non-manual | Full automation end-to-end | CI/CD pipelines, batch processing |
| INTERACTIVE + mixed | Some phases automated, others manual | Automate review, manual generation |

**Why this matters:**
- "Manual provider" ≠ "Interactive mode" (common confusion)
- You can use AI APIs while still maintaining step-by-step control
- You can run fully automated workflows that still require human response creation

---

### Putting It Together

**Actual workflow sequence** (showing when `step` and `approve` are used):

1. **Initialize:** `aiwf init` → creates session
2. **Planning prompt:** `aiwf step` → creates `planning-prompt.md`
3. **[USER ACTION]** Copy prompt to AI, save response to `planning-response.md`
4. **Process planning:** `aiwf step` → validates response, transitions to PLANNED
5. **Approve plan:** `aiwf approve` → copies response to `plan.md`, hashes it, sets `plan_approved=True`
6. **Generation prompt:** `aiwf step` → creates `iteration-1/`, writes `generation-prompt.md`
7. **[USER ACTION]** Copy prompt to AI, save response to `generation-response.md`
8. **Extract code:** `aiwf step` → profile extracts code using `<<<FILE:>>>` markers, writes to `iteration-1/code/` (with `sha256=None`)
9. **Approve code:** `aiwf approve` → hashes all code files, updates `artifact.sha256` values
10. **Review prompt:** `aiwf step` → creates `review-prompt.md`
11. **[USER ACTION]** Copy prompt to AI, save response to `review-response.md`
12. **Process review:** `aiwf step` → validates response, transitions to REVIEWED
13. **Approve review:** `aiwf approve` → hashes review, sets `review_approved=True`, processes verdict
14. **If PASS:** workflow completes
15. **If FAIL:** `aiwf step` → creates `iteration-2/`, writes `revision-prompt.md`
16. **[USER ACTION]** Copy prompt to AI, save response to `revision-response.md`
17. **Extract revised code:** `aiwf step` → extracts code to `iteration-2/code/` (with `sha256=None`)
18. **Approve revised code:** `aiwf approve` → hashes all code files
19. **Back to review:** Cycle repeats from step 10 until PASS

**Pattern you'll see:**
- `aiwf step` → Advances workflow (generates prompts, processes responses)
- **[USER ACTION]** → Copy/paste with AI
- `aiwf approve` → Locks outputs (computes hashes, sets approval flags)

**Key insight:** 
- **`step`** does deterministic work (generate prompts, process responses, write files)
- **`approve`** creates the audit trail (hash what you've reviewed/edited)
- **Hashing happens on approval** - this lets you edit files before they're locked
- **New iterations** are created when review fails (increment happens on REVIEWED → REVISING transition)

**Like all AI-assisted development, output quality depends heavily on prompt quality.** The jpa-mt profile has been refined through real-world usage at Skills Harbor to produce reliable results, but the "garbage in, garbage out" principle still applies.

---

## Quick Start

### Prerequisites

- Python 3.13+
- Poetry (dependency management)

### Installation

```bash
# Clone the repository
git clone https://github.com/scottcm/ai-workflow-engine.git
cd ai-workflow-engine

# Install dependencies
poetry install

# Verify installation
poetry run aiwf --help
```

### Your First Workflow Session

This example uses the **manual provider** (default), which means you'll copy prompts to your AI of choice and paste responses back. This works with:
- Free web interfaces (ChatGPT.com, Claude.ai, Gemini)
- CLI agents (Claude Desktop, Gemini CLI)
- Any AI you have access to

**Benefits of manual mode:**
- No API costs (use free/low-cost AI subscriptions)
- Edit prompts before submission (customize for your needs)
- Use any AI provider (not locked to specific APIs)
- Complete audit trail (all files preserved)

```bash
# 1. Initialize a session
poetry run aiwf init \
  --scope domain \
  --entity Product \
  --table app.products \
  --bounded-context product \
  --schema-file docs/db/01-schema.sql

# Output: <session-id> (e.g., 6e73d8cd7da8461189718154b3e99960)

# 2. Generate planning prompt
poetry run aiwf step <session-id>
# Creates: .aiwf/sessions/<session-id>/iteration-1/planning-prompt.md

# 3. MANUAL STEP: Provide planning response
# - Open: planning-prompt.md
# - Copy content to your AI (ChatGPT, Claude, etc.)
# - Copy AI response
# - Save to: planning-response.md (same directory)

# 4. Process planning response
poetry run aiwf step <session-id>
# Validates response, transitions to PLANNED phase

# 5. Review and approve plan
# - Read: iteration-1/planning-response.md (edit if needed)
poetry run aiwf approve <session-id>
# Hashes plan, transitions to GENERATING

# 6. Continue generation cycle
poetry run aiwf step <session-id>
# Creates: generation-prompt.md

# 7. MANUAL STEP: Provide code generation response
# - Copy generation-prompt.md to AI
# - AI generates code with <<<FILE: filename>>> markers
# - Save response to: generation-response.md

# 8. Extract generated code
poetry run aiwf step <session-id>
# Extracts code to: iteration-1/code/*.java

# 9. Approve generated code
# - Review: iteration-1/code/*.java (edit if needed)
poetry run aiwf approve <session-id>
# Hashes artifacts, ready for review

# 10. Continue review → revision cycle as needed
poetry run aiwf step <session-id>
# ... until workflow reaches COMPLETE

# Check status anytime
poetry run aiwf status <session-id>
```

**Understanding the workflow:**
- `aiwf step` - Advances workflow (generates prompts, processes responses)
- `aiwf approve` - Locks phase outputs (hashes files, sets approval flags)
- **Manual steps** - You copy prompts to AI, paste responses back
- **Editable outputs** - Edit any file before approval to customize results

**Why approval gates?**
- Every output is editable before it becomes input to the next phase
- Fix AI mistakes before they propagate
- Customize generated code to your needs
- Complete control over what gets locked in

---

## What This Project Demonstrates

This project showcases enterprise-grade software engineering practices appropriate for production systems:

### Architecture & Design Patterns

**Implemented Patterns:**
- **Strategy Pattern** (3 uses):
  - `WorkflowProfile` - Different domain/framework implementations (JPA, React, etc.)
  - `AIProvider` - Different AI backends (Claude CLI, Gemini CLI, manual mode)
  - `StandardsProvider` - Different standards retrieval strategies (file-based, RAG, API, Git)
- **Factory Pattern**: `ProfileFactory` and `ProviderFactory` with registration system for dynamic plugin loading
- **Repository Pattern**: `SessionStore` abstracts persistence layer (filesystem, future: database)
- **State Pattern**: Procedural implementation via `WorkflowPhase` enum with phase-specific handlers

**Supporting Patterns:**
- **DTO Pattern**: Pydantic models for type-safe data transfer between layers
- **Dependency Injection**: Constructor-based for testability

**Why These Patterns?**
- **Not applied dogmatically** - each solves a real extensibility or testability challenge
- **Strategy Pattern consistency** - Used across profiles, providers, and standards shows architectural coherence
- **Pragmatic State Pattern** - Enum-based approach simpler than separate state classes while achieving the same goals
- **Factory + Strategy** - Together enable plugin architecture without modifying core engine

### Engineering Practices

- **Clean Architecture**: Layered design with explicit boundaries (Interface → Application → Domain → Infrastructure)
- **SOLID Principles**: Single responsibility, dependency inversion, interface segregation
- **Security by Design**: Path validation, traversal prevention, environment variable expansion
- **Explicit State Management**: Pydantic models with validation, immutable workflow semantics
- **Comprehensive Testing**: 100% passing test suite with unit and integration coverage
- **Living Documentation**: Architecture Decision Records (ADRs) capturing rationale

### Domain Modeling

- **File-Materialized Workflows**: Every output is a file (enables editing, inspection, version control)
- **Approval Gates**: Explicit user control before workflow advancement
- **Deferred Hashing**: Capture user edits before locking artifact state
- **Non-Enforcement**: Hash warnings, never blocks (respects developer autonomy)
- **Iteration Semantics**: Clear rules for when iteration increments (only on revision)

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────┐
│  Interface Layer (CLI)                      │
│  - Click-based commands                     ���
│  - JSON and plain text output               │
├─────────────────────────────────────────────┤
│  Application Layer (Orchestration)          │
│  - WorkflowOrchestrator                     │
│  - ApprovalHandler                          │
│  - StandardsMaterializer                    │
├─────────────────────────────────────────────┤
│  Domain Layer (Core Models & Contracts)     │
│  - WorkflowState, Artifact, ProcessingResult│
│  - WorkflowProfile (interface)              │
│  - AIProvider (interface)                   │
├─────────────────────────────────────────────┤
│  Infrastructure Layer (Implementations)     │
│  - SessionStore (persistence)               │
│  - ProfileFactory, ProviderFactory          │
│  - PathValidator (security)                 │
└─────────────────────────────────────────────┘
```

### Workflow Phases

```
INITIALIZED
     │
     ▼
PLANNING ────────► PLANNED
                     │
                     ▼ (requires plan_approved)
                GENERATING ──────► GENERATED
                                      │
                                      ▼ (requires artifact hashes)
                                  REVIEWING ──────► REVIEWED
                                                       │
              ┌────────────────────────────────────────┤
              │                                         │
              ▼ (FAIL)                                  ▼ (PASS)
         REVISING ──────► REVISED                   COMPLETE
                              │
                              ▼ (requires artifact hashes)
                         REVIEWING
```

### Responsibility Boundaries

**Profiles (Domain-Specific Logic):**
- Generate prompt content (strings)
- Parse AI responses
- Extract code/artifacts
- Return WritePlan (what to write)
- **Never** read or write files
- **Never** mutate workflow state

**Engine (Orchestration):**
- Execute WritePlan
- Write all files (with `sha256=None`)
- Compute hashes (during `approve()`)
- Advance workflow state
- Persist state to disk

This separation enables:
- Profile testing without filesystem mocking
- Easy profile addition (implement interface, register)
- Clear audit trail (engine controls all I/O)

---

## CLI Reference

### Global Options

- `--json` - Emit machine-readable JSON output (available on all commands)

### Commands

#### `aiwf init`

Initialize a new workflow session.

```bash
aiwf init --scope <scope> --entity <entity> --table <table> --bounded-context <context> [options]
```

**Required:**
- `--scope` - Generation scope (`domain` or `vertical` for jpa-mt profile)
- `--entity` - Entity name in PascalCase (e.g., `Product`)
- `--table` - Database table name (e.g., `app.products`)
- `--bounded-context` - Domain context (e.g., `catalog`)

**Optional:**
- `--schema-file` - Path to DDL schema file (required for jpa-mt profile)
- `--dev` - Developer identifier
- `--task-id` - External task/ticket reference

**Output:**
```
<session-id>
```

**Example:**
```bash
aiwf init \
  --scope domain \
  --entity Product \
  --table app.products \
  --bounded-context product \
  --schema-file docs/db/01-schema.sql
```

---

#### `aiwf step`

Advance the workflow by one deterministic step.

```bash
aiwf step <session-id>
```

**Behavior:**
- Generates prompts when entering ING phases (PLANNING, GENERATING, REVIEWING, REVISING)
- Processes responses when files exist
- Reports blocking conditions (awaiting response files)
- Advances phase when conditions met

**Exit Codes:**
- `0` - Success (advanced or already complete)
- `1` - Error
- `2` - Blocked (awaiting artifact)
- `3` - Cancelled

**Output:**
```
phase=PLANNING status=IN_PROGRESS iteration=1 noop_awaiting_artifact=true
.aiwf/sessions/<session-id>/iteration-1/planning-prompt.md
.aiwf/sessions/<session-id>/iteration-1/planning-response.md
```

---

#### `aiwf approve`

Approve current phase outputs, compute hashes, and optionally invoke providers.

```bash
aiwf approve <session-id> [--hash-prompts | --no-hash-prompts]
```

**Phase-Specific Behavior:**

| Phase | Approval Action |
|-------|----------------|
| PLANNING | Hash prompt (optional), call provider, write response |
| PLANNED | Hash `plan.md`, set `plan_approved=True` |
| GENERATING | Hash prompt (optional), call provider, write response |
| GENERATED | Hash all `code/*` files, set artifact `sha256` values |
| REVIEWING | Hash prompt (optional), call provider, write response |
| REVIEWED | Hash `review-response.md`, set `review_approved=True` |
| REVISING | Hash prompt (optional), call provider, write response |
| REVISED | Hash all `code/*` files, set artifact `sha256` values |

**Options:**
- `--hash-prompts` - Force prompt hashing (overrides config)
- `--no-hash-prompts` - Skip prompt hashing (overrides config)

**Example:**
```bash
# Approve with default hashing behavior (from config)
aiwf approve <session-id>

# Force prompt hashing for this approval
aiwf approve <session-id> --hash-prompts
```

---

#### `aiwf status`

Query session state and display key information.

```bash
aiwf status <session-id>
```

**Output:**
```
phase=GENERATING
status=IN_PROGRESS
iteration=1
session_path=.aiwf/sessions/<session-id>
```

**JSON Output:**
```bash
aiwf status <session-id> --json
```

```json
{
  "exit_code": 0,
  "session_id": "abc123...",
  "phase": "GENERATING",
  "status": "IN_PROGRESS",
  "iteration": 1,
  "session_path": ".aiwf/sessions/abc123..."
}
```

---

## Workflow Tutorial

### Complete Example: Domain Entity Generation

**Scenario:** Generate a JPA entity and repository for a Product entity in a multi-tenant product application.

#### Step 1: Initialize Session

```bash
aiwf init \
  --scope domain \
  --entity Product \
  --table app.products \
  --bounded-context product \
  --schema-file docs/db/01-schema.sql
```

**Output:** `6e73d8cd7da8461189718154b3e99960`

**What Happened:**
- Created session directory: `.aiwf/sessions/6e73d8cd.../`
- Generated standards bundle from jpa-mt profile
- Transitioned to PLANNING phase
- Created `session.json` with initial state

---

#### Step 2: Generate Planning Prompt

```bash
aiwf step 6e73d8cd7da8461189718154b3e99960
```

**Output:**
```
phase=PLANNING status=IN_PROGRESS iteration=1 noop_awaiting_artifact=true
.aiwf/sessions/6e73d8cd.../iteration-1/planning-prompt.md
.aiwf/sessions/6e73d8cd.../iteration-1/planning-response.md
```

**What Happened:**
- Generated `planning-prompt.md` with:
  - AI persona and role
  - Standards bundle (JPA, database patterns, etc.)
  - Entity requirements
  - Schema DDL
  - Planning guidelines

**Next Action:** Copy planning-prompt.md to your AI provider (ChatGPT, Claude, etc.)

---

#### Step 3: Provide Planning Response

**Manual Step:**
1. Copy content of `planning-prompt.md`
2. Paste into AI provider (ChatGPT, Claude, Gemini, etc.)
3. Copy AI response
4. Save to `planning-response.md`

**File:** `.aiwf/sessions/6e73d8cd.../iteration-1/planning-response.md`

---

#### Step 4: Process Planning Response

```bash
aiwf step 6e73d8cd7da8461189718154b3e99960
```

**Output:**
```
phase=PLANNED status=IN_PROGRESS iteration=1 noop_awaiting_artifact=false
```

**What Happened:**
- Validated planning-response.md exists and is non-empty
- Transitioned to PLANNED phase
- Workflow now awaits plan approval

---

#### Step 5: Review and Approve Plan

**Manual Review:**
```bash
# Read the planning response
cat .aiwf/sessions/6e73d8cd.../iteration-1/planning-response.md

# Edit if needed (make any corrections before approval)
```

**Approve:**
```bash
aiwf approve 6e73d8cd7da8461189718154b3e99960
```

**What Happened:**
- Copied `planning-response.md` → `plan.md` (session root)
- Computed SHA-256 hash of plan.md
- Set `plan_approved=True`
- Workflow ready to advance to GENERATING

---

#### Step 6: Enter Generation Phase

```bash
aiwf step 6e73d8cd7da8461189718154b3e99960
```

**Output:**
```
phase=GENERATING status=IN_PROGRESS iteration=1 noop_awaiting_artifact=true
.aiwf/sessions/6e73d8cd.../iteration-1/generation-prompt.md
.aiwf/sessions/6e73d8cd.../iteration-1/generation-response.md
```

**What Happened:**
- Created `iteration-1/` directory
- Generated `generation-prompt.md` with:
  - Approved plan
  - Standards bundle
  - Code generation guidelines
  - Output format instructions (`<<<FILE: filename>>>`)

---

#### Step 7: Provide Generation Response

**Manual Step:**
1. Copy `generation-prompt.md` → AI provider
2. AI generates code with `<<<FILE: Product.java>>>` markers
3. Save response to `generation-response.md`

**Expected Format:**
```markdown
Here's the implementation:

<<<FILE: Product.java>>>
package com.skillsharbor.catalog.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
// ... (complete entity code)
>>>

<<<FILE: ProductRepository.java>>>
package com.skillsharbor.catalog.domain;

import org.springframework.data.jpa.repository.JpaRepository;
// ... (complete repository code)
>>>
```

---

#### Step 8: Extract Generated Code

```bash
aiwf step 6e73d8cd7da8461189718154b3e99960
```

**Output:**
```
phase=GENERATED status=IN_PROGRESS iteration=1 noop_awaiting_artifact=false
```

**What Happened:**
- Parsed `generation-response.md`
- Extracted code blocks using `<<<FILE:>>>` markers
- Wrote files to `iteration-1/code/`:
  - `Product.java`
  - `ProductRepository.java`
- Created artifact metadata (with `sha256=None`)
- Transitioned to GENERATED phase

---

#### Step 9: Approve Generated Code

**Manual Review:**
```bash
# Review generated files
ls -la .aiwf/sessions/6e73d8cd.../iteration-1/code/
cat .aiwf/sessions/6e73d8cd.../iteration-1/code/Product.java

# Edit if needed (fix any issues before approval)
```

**Approve:**
```bash
aiwf approve 6e73d8cd7da8461189718154b3e99960
```

**What Happened:**
- Computed SHA-256 for each file in `iteration-1/code/`
- Updated artifact metadata with hashes
- Workflow ready for review

---

#### Step 10: Review Phase

```bash
# Generate review prompt
aiwf step 6e73d8cd7da8461189718154b3e99960

# Provide review response (same copy/paste workflow)
# ... save to review-response.md

# Process review
aiwf step 6e73d8cd7da8461189718154b3e99960
```

**What Happened:**
- Generated `review-prompt.md` with standards and code files
- Parsed review response for `@@@REVIEW_META` block
- Extracted verdict (PASS/FAIL)
- Transitioned to REVIEWED phase

---

#### Step 11: Final Approval

```bash
aiwf approve 6e73d8cd7da8461189718154b3e99960
```

**What Happened:**
- If verdict=PASS: Workflow transitions to COMPLETE
- If verdict=FAIL: Workflow increments iteration and transitions to REVISING

---

### Session Directory Structure

After a complete workflow:

```
.aiwf/sessions/6e73d8cd.../
├── session.json                # Workflow state
├── standards-bundle.md         # Immutable standards
├── plan.md                     # Approved plan (session root)
│
├── iteration-1/
│   ├── planning-prompt.md
│   ├── planning-response.md
│   ├── generation-prompt.md
│   ├── generation-response.md
│   ├── review-prompt.md
│   ├── review-response.md
│   └── code/
│       ├── Product.java
│       └── ProductRepository.java
│
└── iteration-2/                # Created only if revision needed
    ├── revision-prompt.md
    ├── revision-response.md
    ├── review-prompt.md
    ├── review-response.md
    └── code/
        ├── Product.java        # Revised version
        └── ProductRepository.java
```

---

## Configuration

### Configuration File Locations

Configuration is loaded with the following precedence (highest wins):

1. **CLI flags** (e.g., `--dev`, `--hash-prompts`)
2. **Project-specific:** `./.aiwf/config.yml`
3. **User-wide:** `~/.aiwf/config.yml`
4. **Built-in defaults**

### Example Configuration

**`.aiwf/config.yml`:**
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

### Configuration Options

#### `profile`

Workflow profile to use. Currently supported:
- `jpa-mt` - JPA multi-tenant domain generation

#### `providers`

AI provider for each workflow role:
- `planner`, `generator`, `reviewer`, `reviser`

Currently supported providers:
- `manual` - Human-in-the-loop (prompt/response files)

#### `hash_prompts`

Whether to hash prompt files during approval:
- `false` (default) - Only hash outputs (plan, code, reviews)
- `true` - Also hash prompts for complete audit trail

Can be overridden via CLI: `--hash-prompts` / `--no-hash-prompts`

#### `dev`

Optional developer identifier (passed to templates):
- `null` (default) - No developer ID
- `"Scott Mulcahy"` - Your name
- CLI flag overrides: `--dev "Scott Mulcahy"`

---

## JPA Multi-Tenant Profile

The `jpa-mt` profile is the first production profile, designed for Java-focused teams building multi-tenant SaaS applications.

**What it does:** Generates complete, production-ready Java/Spring Data JPA code for multi-tenant database entities. This includes proper tenant isolation, Row-Level Security (RLS) patterns, and Spring Data repositories.

**Why it exists:** The profile encapsulates architectural decisions and best practices for multi-tenant JPA applications into reusable AI prompts, eliminating the need to reinvent patterns for every entity.

### Target Stack

- Java 21
- Spring Data JPA 3.x
- PostgreSQL 16+ with Row-Level Security (RLS)
- Multi-tenant architecture (tenant_id foreign keys, RLS policies)

### Supported Scopes

#### Domain Scope

Generates domain layer only:
- JPA Entity with tenant awareness
- Spring Data Repository

**Use Case:** Adding entities to existing applications

**Command:**
```bash
aiwf init --scope domain --entity Product --table app.products --bounded-context product
```

#### Vertical Scope

Generates complete feature implementation:
- Entity → Repository → Service → Controller
- DTOs and Mappers
- Complete vertical slice

**Use Case:** Full-stack feature implementation

**Command:**
```bash
aiwf init --scope vertical --entity Product --table app.products --bounded-context product
```

### Template System

The jpa-mt profile uses a three-tier layered template system:

**Layer 1: Shared (_shared/)**
- `base.md` - AI persona, metadata, file attachments
- `fallback-rules.md` - Deterministic defaults

**Layer 2: Phase (_phases/)**
- `planning-guidelines.md`
- `generation-guidelines.md`
- `review-guidelines.md`
- `revision-guidelines.md`

**Layer 3: Scope (planning/, generation/, etc.)**
- `domain.md` - Domain-specific requirements
- `vertical.md` - Vertical-specific requirements

**Composition:** Templates use `{{include: ...}}` directives to compose layers:

```markdown
{{include: _shared/base.md}}
{{include: _phases/planning-guidelines.md}}

# Domain-Specific Content
...
```

### Standards Management

Standards are scope-aware and organized by layer:

```yaml
scopes:
  domain:
    layers: [entity, repository]
  vertical:
    layers: [entity, repository, service, controller]

layer_standards:
  _universal: [CORE_CONVENTIONS.md]
  entity: [JPA_ENTITY.md]
  repository: [JPA_REPOSITORY.md]
  service: [SERVICE_LAYER.md]
  controller: [REST_CONTROLLER.md]
```

Standards are concatenated in order with deduplication, creating a scope-appropriate bundle.

---

### Quality Considerations

**Like all AI-assisted development, output quality depends on prompt quality.** The jpa-mt profile has been refined through real-world usage at Skills Harbor to produce reliable results, but several factors affect quality:

**Prompt Quality Factors:**
- **Standards completeness** - Well-documented coding conventions improve consistency
- **Schema quality** - Clear, well-structured DDL helps AI understand data model
- **Context clarity** - Explicit entity relationships and business rules reduce ambiguity
- **AI model choice** - Different models have different strengths (GPT-4, Claude Opus, etc.)

**Profile Design Choices:**
- **Layered templates** - Separate shared, phase-specific, and scope-specific content
- **Explicit standards** - JPA patterns, Spring Data conventions, multi-tenancy rules
- **Structured extraction** - `<<<FILE:>>>` markers for reliable code parsing
- **Review metadata** - Structured `@@@REVIEW_META` blocks for deterministic parsing

**Best Practices:**
- Start with high-quality standards documents (see `docs/samples/`)
- Provide complete, accurate schema DDL
- Review planning responses before approval (catch misunderstandings early)
- Edit prompts if AI consistently misunderstands requirements
- Iterate on standards based on review feedback

**Remember:** The engine provides workflow orchestration and file management. The profile provides prompt templates and extraction logic. **You** provide the domain knowledge and quality standards that make AI output production-ready.

---

## Extending the Engine

The engine is designed for extension through two primary mechanisms: **profiles** (language/tech specifics) and **providers** (AI integration).

### Adding New Profiles

**What profiles do:** Profiles implement the language/technology-specific knowledge needed for AI to produce code. They translate workflow context into appropriate prompts and extract code from AI responses.

**Profile responsibilities:**
- Generate prompts using domain-specific templates
- Parse AI responses and extract code/artifacts
- Apply language-specific standards and conventions
- Return structured results (WritePlan, ProcessingResult)
- **Never** perform file I/O (engine's responsibility)
- **Never** mutate workflow state (engine's responsibility)

**Creating a new profile:**

Profiles encapsulate all language/framework-specific generation logic. The engine is completely agnostic to what language you're generating.

**Example: React/TypeScript Profile**

```python
# profiles/react_ts/react_ts_profile.py
from aiwf.domain.profiles.workflow_profile import WorkflowProfile
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.write_plan import WritePlan, WriteOp

class ReactTsProfile(WorkflowProfile):
    """Generates React components with TypeScript."""
    
    def generate_planning_prompt(self, context: dict) -> str:
        """Generate component planning prompt with React patterns."""
        return self._render_template('planning/component.md', context)
    
    def generate_generation_prompt(self, context: dict) -> str:
        """Generate code generation prompt with TypeScript guidance."""
        return self._render_template('generation/component.md', context)
    
    def process_generation_response(self, content: str, session_dir, iteration: int) -> ProcessingResult:
        """Extract .tsx and .css files from response."""
        files = self._extract_code_blocks(content)
        
        writes = [
            WriteOp(path=f"code/{name}", content=code)
            for name, code in files.items()
        ]
        
        return ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=writes)
        )
    
    # ... implement review and revision methods

# Register in profiles/react_ts/__init__.py
from aiwf.domain.profiles.profile_factory import ProfileFactory
ProfileFactory.register('react-ts', ReactTsProfile)
```

**Profile structure:**
```
profiles/react_ts/
├── __init__.py              # Registration
├── react_ts_profile.py      # Profile implementation
├── config.yml               # Standards configuration
├── templates/
│   ├── _shared/             # Common content
│   ├── _phases/             # Phase-specific guidelines
│   ├── planning/            # Planning templates by scope
│   ├── generation/          # Generation templates
│   ├── review/              # Review templates
│   └── revision/            # Revision templates
└── tests/
    └── test_react_ts_profile.py
```

**What you control:**
- Prompt templates (how you instruct the AI)
- Code extraction logic (parsing AI responses)
- Standards selection (what coding rules apply)
- File structure (what gets written where)

**What the engine handles:**
- Workflow orchestration
- File I/O (all writes)
- State persistence
- Approval gates
- Iteration management

---

### Adding New AI Providers

**What providers do:** Providers abstract away how AI is accessed—whether via API, CLI agent, or manual workflow. They handle the mechanics of prompt delivery and response retrieval.

**Creating a new provider:**

Providers implement the `AIProvider` interface for automated execution. The `manual` provider serves as the reference implementation.

**Current providers:**
- `manual` - Human-in-the-loop (creates files, user handles AI interaction)

**Example: Claude CLI Provider**

```python
from aiwf.domain.providers.ai_provider import AIProvider
import subprocess

class ClaudeCliProvider(AIProvider):
    """Automated provider using Claude Desktop agent."""
    
    async def generate(self, prompt: str, context: dict | None) -> str:
        """Call Claude CLI agent and return response."""
        result = subprocess.run(
            ['claude', '--prompt', prompt],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise ProviderError(f"Claude CLI failed: {result.stderr}")
        
        return result.stdout

# Register in infrastructure/providers/__init__.py
from aiwf.domain.providers.provider_factory import ProviderFactory
ProviderFactory.register('claude-cli', ClaudeCliProvider)
```

**Configuration:**
```yaml
# .aiwf/config.yml
providers:
  planner: claude-cli      # Automated via Claude
  generator: manual         # User copies to AI manually
  reviewer: claude-cli      # Automated via Claude
  reviser: manual           # User copies to AI manually
```

**Provider responsibilities:**
- Accept prompt content (string)
- Invoke AI (API, CLI, no-op for manual)
- Return response content (string)
- Handle errors gracefully

**Provider non-responsibilities:**
- File I/O (engine handles prompt/response files)
- State mutation (engine tracks everything)
- Prompt generation (profiles handle this)

**Why providers are separate:**
- Mix automated and manual steps in same workflow
- Swap AI services without changing profiles
- Support CLI agents, APIs, and manual workflows
- Test profiles without calling real AI

---

### Design Principles

**Profile isolation:**
- Profiles are pure functions of context → prompts or WritePlans
- No side effects (file I/O, state mutation)
- Deterministic and testable without mocking

**Engine orchestration:**
- Engine owns all file I/O
- Engine owns all state transitions
- Engine enforces approval gates
- Engine persists everything

**Provider abstraction:**
- Providers handle AI communication only
- Profiles never call providers directly
- Engine mediates all provider interactions
- Manual provider is always available

This separation of concerns enables:
- Profile reuse across providers
- Provider reuse across profiles  
- Testing without real AI or filesystem
- Clear responsibility boundaries

---

## Documentation

### Architecture Decision Records

- [ADR-0001: Architecture Overview](docs/adr/0001-architecture-overview.md) - Patterns, layers, responsibility boundaries
- [ADR-0002: Template Layering System](docs/adr/0002-template-layering-system.md) - Template composition with includes
- [ADR-0003: Workflow State Validation](docs/adr/0003-workflow-state-validation.md) - Pydantic usage rationale
- [ADR-0004: Structured Review Metadata](docs/adr/0004-structured-review-metadata.md) - Review parsing specification

### Specifications

- [API-CONTRACT.md](API-CONTRACT.md) - Complete CLI interface specification
- [TEMPLATE_RENDERING.md](profiles/jpa_mt/TEMPLATE_RENDERING.md) - Template system guide

### Additional Resources

- [CHANGELOG.md](CHANGELOG.md) - Version history and release notes
- Sample standards: `docs/samples/`
- Database setup: `docker-compose.yml` (PostgreSQL 16 with sample multi-tenant schema)

---

## Development Setup

### Prerequisites

- Python 3.13+
- Poetry 1.7+
- (Optional) Docker for PostgreSQL test database

### Installation

```bash
# Clone repository
git clone https://github.com/scottcm/ai-workflow-engine.git
cd ai-workflow-engine

# Install dependencies (includes dev dependencies)
poetry install

# Activate virtual environment
poetry shell
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aiwf --cov-report=html

# Run specific test file
pytest tests/unit/application/test_workflow_orchestrator_initialize_run.py

# Run tests matching pattern
pytest -k "test_approval"
```

### Code Quality

```bash
# Type checking
mypy aiwf

# Linting
ruff check aiwf

# Auto-fix
ruff check --fix aiwf
```

### Development Database (Optional)

A PostgreSQL database with sample schema is provided for testing and experimentation. This database includes:
- Multi-tenant schema patterns (tenant isolation, RLS policies)
- Sample tables matching the jpa-mt profile's target patterns
- Seed data for realistic testing
```bash
# Start PostgreSQL with sample schema
docker-compose up -d

# Connection details:
# Host: localhost
# Port: 5432
# Database: aiwf_test
# User: aiwf_user
# Password: aiwf_pass

# The schema includes:
# - app.tenants      : Tenant entity
# - global.tiers     : Global lookup table (no tenant_id)
# - app.products     : Tenant-scoped table with RLS

# Stop when done
docker-compose down
```

**Use cases:**
- Test generated JPA entities against real PostgreSQL
- Experiment with the workflow using included `docs/db/01-schema.sql`
- Understand multi-tenant patterns that jpa-mt profile targets

**Note:** The database is optional. The workflow engine works entirely with files and doesn't require database connectivity.

---

## Known Limitations

### Not Yet Implemented (Planned for 1.0.0)

These features are planned but not critical to core functionality:

- `aiwf list` - List sessions with filtering
- `aiwf profiles` - List available profiles  
- `aiwf providers` - List available AI providers

### Intentional Design Choices

These are features we've chosen not to implement (at least initially):

- **Manual provider by design** - Copy/paste workflow provides budget-friendly access to any AI while maintaining full control over prompts and responses
- **Single profile initially** - Extension point exists; additional profiles are encouraged as community contributions
- **No multi-user coordination** - Designed for single developer workflows
- **No AI code sandboxing** - Security is downstream integration responsibility

### Future Enhancements (Post-1.0)

Features under consideration for future releases:

- Automated AI provider integrations (Claude CLI, Gemini CLI)
- Additional profiles (React/TypeScript, Python/FastAPI, etc.)
- Plugin discovery and registration system
- Advanced validation and linting
- Performance optimizations

**Note:** The manual provider is not a limitation—it's a feature that enables:
- Use of free AI subscriptions (ChatGPT.com, Claude.ai, Gemini)
- Support for any AI provider (not locked to specific vendors)
- Full prompt editing before submission
- Review/modify AI responses before processing
- Complete workflow transparency (all files visible)
- Zero API costs

---

## Project Status

**Current Release: v0.9.0** 🎉

Fully functional AI workflow orchestration with manual mode. All core features complete:
- ✅ Multi-phase workflows (planning → generation → review → revision)
- ✅ Approval system with deferred hashing for artifact validation
- ✅ JPA multi-tenant profile with comprehensive standards
- ✅ CLI interface (`init`, `step`, `approve`, `status`)
- ✅ Session persistence and resumability
- ✅ Iteration tracking with complete audit trail
- ✅ Path validation and security boundaries

### What's Next: v1.0.0

**Enhanced CLI:**
- `aiwf list` - List all workflow sessions
- `aiwf profiles` - Show available profiles
- `aiwf providers` - Show available AI providers
- Improved error messages and user feedback

**Extensibility & Integration:**
- Event system for IDE extension support (Observer pattern)
- Refactored approval handling for easier extensibility (Chain of Responsibility)
- Extension/plugin API documentation
- VS Code extension protocol specification

### Future Enhancements (v2.0.0+)

- **Additional Profiles**: React components, Python/FastAPI, Go microservices
- **Automated AI Providers**: Direct integration with Claude CLI, Gemini CLI
- **CI/CD Integration**: Webhook support for automated workflows
- **Advanced Features**: Sub-workflows, parallel generation, custom validation hooks

---

## Contributing

Contributions are welcome! This is a portfolio project demonstrating architecture patterns, but improvements and additional profiles are encouraged.

**Areas for Contribution:**
- New workflow profiles (React, Python, Go, etc.)
- Additional AI provider integrations
- Enhanced validation and linting
- Documentation improvements
- Bug reports and feature requests

**Before Contributing:**
- Review [ADR-0001](docs/adr/0001-architecture-overview.md) for architectural principles
- Ensure tests pass: `pytest`
- Follow existing code style: `ruff check`
- Add tests for new features

---

## License

MIT License

Copyright (c) 2024 Scott Mulcahy

See [LICENSE](LICENSE) file for details.

---

## Support

**Issues:** https://github.com/scottcm/ai-workflow-engine/issues  
**Discussions:** https://github.com/scottcm/ai-workflow-engine/discussions

**About the Author:**  
Scott Mulcahy - CTO at Skills Harbor LLC  
Portfolio: https://github.com/scottcm  
Email: 60183134+scottcm@users.noreply.github.com

---

## Acknowledgments

- Built to solve real-world needs at Skills Harbor
- Inspired by enterprise architecture patterns from production experience
- Designed for demonstration of software engineering best practices
- Special thanks to the open source community for foundational tools (Python, Poetry, Pydantic, Click, pytest)

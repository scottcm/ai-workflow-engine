# AI Workflow Engine

**A project demonstrating enterprise architecture patterns in an AI-assisted development workflow engine**

> ⚙️ **Project Status: Active Development**  
> A production workflow engine demonstrating enterprise architecture patterns built to orchestrate AI-assisted code generation for multi-tenant SaaS applications. Designed around budget constraints (works with consumer AI subscriptions), real architectural complexity (multi-tenant patterns, state management), and tight timelines.

The architecture deliberately demonstrates Strategy, Factory, Chain of Responsibility, Builder, Command, Adapter, and Template Method patterns - not because patterns are the goal, but because they solve real extensibility, testability, and maintainability challenges in this domain.

---

## Table of Contents

- [Overview](#overview)
- [What This Project Demonstrates](#what-this-project-demonstrates)
- [The Problem It Solves](#the-problem-it-solves)
- [Why This Approach?](#why-this-approach)
- [Architecture Overview](#architecture-overview)
  - [Key Patterns](#key-patterns)
- [Language and Framework Agnostic](#language-and-framework-agnostic)
- [Profile System](#profile-system)
  - [JPA Multi-Tenant Profile (`jpa-mt`)](#jpa-multi-tenant-profile-jpa-mt)
  - [Why Java/Spring Data JPA First?](#why-javaspring-data-jpa-first)
  - [Profile Architecture](#profile-architecture)
- [Session Workflow](#session-workflow)
  - [Directory Structure](#directory-structure)
  - [Workflow Phases](#workflow-phases)
  - [Interactive Mode Example](#interactive-mode-example)
- [CLI Overview](#cli-overview)
- [Configuration](#configuration)
- [Standards Management](#standards-management)
  - [Immutability](#immutability)
  - [Bundling Strategy](#bundling-strategy)
  - [Validation](#validation)
- [Security](#security)
  - [Input Validation](#input-validation)
  - [Path Validation](#path-validation)
- [Documentation](#documentation)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Project Goals](#project-goals)
- [Extending the Engine](#extending-the-engine)
  - [Adding New Profiles](#adding-new-profiles)
  - [Adding New AI Providers](#adding-new-ai-providers)
  - [Adding New Scopes](#adding-new-scopes)
- [Companion VS Code Extension](#companion-vs-code-extension)
- [Development Database (Postgres via Docker)](#development-database-postgres-via-docker)
- [Development Setup](#development-setup)
- [License](#license)
- [Support](#support)

---

## Overview

The AI Workflow Engine orchestrates multi-phase code generation workflows across multiple AI providers.  
It supports both:

- **Interactive mode** — generates prompt files for manual use with web UIs  
- **Automated mode** — executes workflows using local CLI agents

The system is architected as a modular, extensible engine with clear responsibilities and deliberate use of enterprise design patterns.

---

## What This Project Demonstrates

- **Deliberate application of 8 design patterns**  
  Strategy, Factory, Chain of Responsibility, Builder, Command, Adapter, Template Method
- **Layered architecture**  
  Interface → Application → Domain → Infrastructure
- **Extensible profile system**  
  Swap entire workflow domains without modifying the engine core
- **Pluggable AI providers**  
  Claude, Gemini, Manual (prompt-only), with future expansions
- **Stateful, resumable workflows**  
  JSON-based workflow state with checkpoints and iteration tracking
- **Dual execution modes**  
  Manual (prompt/paste) and automated (CLI provider calls)
- **Language-agnostic design**  
  Core engine supports any target language through profiles
- **Security by design**  
  Input sanitization, path validation, and environment variable safety

The structure and documentation are designed to make architectural decisions, design rationale, and system-level thinking easy to evaluate at a glance.

---

## The Problem It Solves

AI-assisted development often requires:

1. Planning  
2. Code generation  
3. Code review or critique  
4. One or more revision loops

Most ad-hoc workflows:

- Hard-code a single AI provider  
- Mix prompts, scripts, and output logic together  
- Do not explicitly model workflow phases  
- Cannot switch between manual and automated execution  
- Cannot reuse logic across different domains (e.g., ORM vs API generation)
- Lose audit trail of what was generated and why

The AI Workflow Engine addresses these issues by:

- Modeling workflows as a **phase pipeline** using Chain of Responsibility  
- Allowing different AI providers to be assigned to different roles  
- Supporting both fully automated and partially manual execution modes  
- Encapsulating domain-specific behavior in **profiles** rather than in core logic
- Preserving complete audit trail in iteration-based directories
- Making standards immutable within a session to prevent corruption

---

## Why This Approach?

**Budget Reality**: Many startups can't afford pay-as-you-go AI APIs. This engine works with:
- Consumer subscription products (ChatGPT, Claude Pro, Gemini Advanced)
- Local CLI agents (claude, gemini)
- Manual copy-paste workflows

**Collaboration Ready**: Designed with clear contracts for a VS Code extension developer to build against.

**Real-World Use**: Built to drive actual code generation with multi-tenant patterns for a SaaS application.

**Auditability**: Full audit trail preserved - every prompt, response, and iteration tracked for debugging and improvement.

---

## Architecture Overview

    Interface Layer (CLI)
          ↓
    Application Layer (Services & Execution)
          ↓
    Domain Layer (Core Models, Patterns, Profiles)
          ↓
    Infrastructure Layer (Adapters: AI providers, filesystem, legacy scripts)

### Key Patterns

- **Strategy** — Swap AI providers and workflow profiles at runtime  
- **Factory** — Instantiate providers and profiles from configuration  
- **Chain of Responsibility** — Compose workflow phases as a pipeline  
- **Builder** — Fluent, safe construction of handler chains  
- **Command** — Encapsulate operations such as prompt prep and bundle extraction  
- **Adapter** — Integrate CLI tools and legacy scripts behind stable interfaces  
- **Template Method** — Shared prompt skeletons with overridable sections  

Full explanations are available in the ADRs.

---

## Language and Framework Agnostic

The engine core is **language-agnostic**. Profiles encapsulate all language and framework-specific logic:

**Current Profile:**
- `jpa-mt` - Java/Spring Data JPA with multi-tenant patterns

**Possible Future Profiles:**
- Python/SQLAlchemy
- C#/Entity Framework Core  
- TypeScript/Prisma
- Go/GORM
- Ruby/ActiveRecord

Each profile defines its own templates, standards, and validation rules appropriate to its target stack. The engine orchestrates phases and manages state regardless of the target language.

---

## Profile System

Profiles encapsulate complete workflow configurations for different code generation domains.

### JPA Multi-Tenant Profile (`jpa-mt`)

**Target Stack:** Java 21, Spring Data JPA, PostgreSQL  
**Tenancy Model:** Multi-tenant with row-level security

**Supported Scopes:**

1. **`domain`** — Entity + Repository only
   - Generates: JPA Entity, Spring Data Repository
   - Use case: Domain layer for existing applications

2. **`vertical`** — Complete feature implementation
   - Generates: Entity → Repository → Service → Controller + DTOs/Mappers
   - Use case: Full-stack feature implementation

### Why Java/Spring Data JPA First?

1. Demonstrates real-world complexity (multi-tenancy, RLS)
2. Matches the actual production architecture requirements at Skills Harbor, where I serve as CTO
3. Java's verbosity showcases code generation value
4. Multi-tenant patterns are common in enterprise SaaS

The same architectural patterns apply to other languages/ORMs through additional profiles.

### Profile Architecture

Profiles are self-contained and define:
- **Configuration** — Scopes, layers, standards mapping
- **Prompt templates** — How to structure AI requests (phase + scope specific)
- **Standards bundles** — Domain-specific coding standards (immutable per session)
- **Bundle parsing** — Extract generated code from AI responses
- **Validation rules** — What to check in generated code

**Key Design Decision:** Standards selection and bundling is a **profile responsibility**, not an engine concern. Profiles can use:
- Layer-based standards mapping (jpa-mt approach)
- Static file concatenation
- Tag-based dynamic selection
- Template-based assembly

---

## Session Workflow

### Directory Structure

**Session directory** (`.aiwf/sessions/{session-id}/`):
```
.aiwf/sessions/20241206-143045-b7k2/
├── session.json                # State tracking
├── workflow.log                # Execution log
├── standards-bundle.md         # Immutable standards
│
├── iteration-1/                # First generation attempt
│   ├── planning-prompt.md
│   ├── planning-response.md
│   ├── generation-prompt.md
│   ├── generation-response.md
│   ├── review-prompt.md
│   ├── review-response.md
│   └── code/
│       ├── Entity.java
│       └── EntityRepository.java
│
└── iteration-2/                # Revision (if needed)
    └── [same structure]
```

**Target directory** (if configured):
```
{target_root}/Tier/domain/
├── standards-bundle.md         # Standards used
├── Tier.java                   # Final code (easy access)
├── TierRepository.java
├── iteration-1/                # Full audit trail
└── iteration-2/
```

### Workflow Phases

1. **Planning** — Design entity structure and relationships
2. **Generation** — Generate code following approved plan
3. **Review** — Validate against standards and best practices
4. **Revision** — Fix issues identified in review (loops until pass)

### Interactive Mode Example

```bash
# Set up environment
export STANDARDS_DIR="/path/to/your/standards"
export ARTIFACT_ROOT="/path/to/your/project/ai-artifacts"

# Start workflow
aiwf run --profile jpa-mt --scope domain --entity Tier

# Engine creates iteration-1/planning-prompt.md and standards-bundle.md
# You attach files to AI, save response to iteration-1/planning-response.md

# Continue to generation
aiwf step generate --session {session-id}

# Attach generation-prompt.md, planning-response.md, standards-bundle.md to AI
# Save code bundle to generation-response.md

# Review generated code
aiwf step review --session {session-id}

# If review fails, revise
aiwf step revise --session {session-id}
# Creates iteration-2/ with revision prompts and responses
```

---

## CLI Overview

The engine exposes seven primary CLI commands:

1. **aiwf new** — Initialize workflow session without executing phases
2. **aiwf run** — Create session and start workflow
3. **aiwf step <phase>** — Execute single workflow phase (interactive mode)
4. **aiwf resume** — Continue existing workflow from current state
5. **aiwf status** — Get detailed session status
6. **aiwf list** — List all workflow sessions
7. **aiwf profiles** — List available profiles and their capabilities

See `API-CONTRACT.md` for complete CLI specification.

---

## Configuration

Profiles use YAML configuration with environment variable support:

```yaml
# profiles/jpa-mt/config.yml

standards:
  root: "${STANDARDS_DIR}"

artifacts:
  session_root: ".aiwf/sessions"
  target_root: "${ARTIFACT_ROOT}"
  target_structure: "{entity}/{scope}"
  
  copy_strategy:
    iterations: true      # Copy all iterations (audit trail)
    audit_trail: true     # Include prompts & responses
    standards: true       # Copy standards bundle

scopes:
  domain:
    description: "Multi-tenant JPA domain layer (Entity + Repository)"
    layers: [entity, repository]
    
  vertical:
    description: "Complete feature implementation (all layers)"
    layers: [entity, repository, service, controller, dto, mapper]

layer_standards:
  _universal:
    - PACKAGES_AND_LAYERS.md
  entity:
    - ORG.md
    - JPA_AND_DATABASE.md
    - ARCHITECTURE_AND_MULTITENANCY.md
    - NAMING_AND_API.md
  # ... additional layer mappings
```

**Key Features:**
- Environment variable expansion (`${VAR_NAME}`)
- Pydantic validation for early error detection
- Layer-based standards deduplication
- Flexible target directory structure
- Configurable artifact copying

---

## Standards Management

### Immutability

Standards are bundled once at session creation and **cannot change** during the workflow. This prevents corruption from mid-session standards updates.

### Bundling Strategy

The `jpa-mt` profile uses layer-based standards mapping:

1. Collect all layers for requested scope (e.g., `[entity, repository]`)
2. Gather standards files for each layer from `layer_standards` config
3. Add universal standards (`_universal` key)
4. Deduplicate (files referenced multiple times loaded once)
5. Concatenate with separators: `--- FILENAME.md ---`

**Example bundle for `domain` scope:**
```markdown
--- PACKAGES_AND_LAYERS.md ---
[content]

--- ORG.md ---
[content]

--- JPA_AND_DATABASE.md ---
[content]
```

### Validation

Engine validates:
- Standards root exists and is accessible
- All referenced files exist
- No path traversal in filenames
- Bundle hasn't changed between iterations

---

## Security

### Input Validation

The engine includes shared validation utilities (`aiwf/domain/validation/path_validator.py`):

- **Entity names** — Alphanumeric, hyphens, underscores only
- **Path components** — No `../`, `/`, or `\` in user inputs
- **Environment variables** — Safe expansion with undefined var detection
- **Template variables** — Only allowed variables in target structure
- **Standards files** — Must be within standards root (no traversal)

### Path Validation

All paths validated for:
- Absolute path requirements
- Existence checks
- Read/write permissions
- Path traversal prevention

Profiles can extend base validation with domain-specific rules.

---

## Documentation

**Architecture:**
- `docs/adr/0001-architecture-overview.md` — Complete architecture decisions
- `docs/adr/0001-architecture-overview-phase2.md` — Phase 2 design updates

**API:**
- `API-CONTRACT.md` — CLI interface specification
- `API-CONTRACT-phase2-updates.md` — Session structure updates

**Profiles:**
- `profiles/jpa-mt/README.md` — Complete jpa-mt profile guide
- `profiles/jpa-mt/config.yml` — Configuration with inline documentation

**Development:**
- `aiwf/domain/validation/path_validator.py` — Security utilities reference

Additional design rationale and commentary are available in GitHub Discussions.

---

## Tech Stack

- **Python 3.13** — Modern Python with full Pydantic v2 support
- **Pydantic** — Data modeling and validation
- **Click** — CLI interface
- **Poetry** — Dependency management
- **pytest** — Testing framework

---

## Project Structure

```
ai-workflow-engine/
├── aiwf/                        # Engine core
│   ├── domain/                  # Models, interfaces, patterns
│   │   ├── models/              # WorkflowState, Artifact
│   │   ├── providers/           # AIProvider interface + factory
│   │   ├── profiles/            # WorkflowProfile interface + factory
│   │   ├── persistence/         # SessionStore
│   │   └── validation/          # Security utilities
│   ├── application/             # Services, orchestration
│   ├── infrastructure/          # Providers, adapters
│   │   └── ai/                  # AI provider implementations
│   └── interface/               # CLI commands
├── profiles/                    # Profile implementations
│   └── jpa-mt/                  # JPA multi-tenant profile
│       ├── config.yml           # Profile configuration
│       ├── profile.py           # Profile implementation
│       ├── templates/           # Prompt templates
│       │   ├── planning/
│       │   ├── generation/
│       │   ├── review/
│       │   └── revision/
│       └── README.md            # Profile documentation
├── docs/
│   └── adr/                     # Architecture Decision Records
├── tests/
│   ├── unit/
│   └── integration/
├── API-CONTRACT.md              # CLI specification
└── README.md                    # This file
```

---

## Project Goals

This project is intentionally built to demonstrate:

1. Thoughtful, enterprise-grade architectural decisions  
2. Appropriate and justified use of design patterns  
3. Clean, maintainable code aligned with SOLID principles  
4. Comprehensive documentation (ADRs, profiles, API contracts)  
5. Extensibility for additional workflows and providers  
6. A stable integration surface for a VS Code extension and other tools
7. Language-agnostic design allowing profiles for any tech stack
8. Security by design with shared validation utilities

---

## Extending the Engine

### Adding New Profiles

1. Create profile directory under `profiles/`
2. Create `config.yml` with scopes and standards mapping
3. Implement `WorkflowProfile` interface in `profile.py`
4. Create prompt templates for each phase and scope
5. Document profile in `README.md`

Profiles can target any language/framework. Use `jpa-mt` as a reference implementation.

### Adding New AI Providers

1. Implement `AIProvider` interface
2. Handle provider-specific authentication and API calls
3. Register provider in `ProviderFactory`
4. Update configuration schema

Providers are Strategy pattern implementations swapped at runtime.

### Adding New Scopes

Add scope to profile's `config.yml`:

```yaml
scopes:
  custom-scope:
    description: "Your custom generation scope"
    layers: [layer1, layer2, layer3]
```

Create corresponding templates in `templates/planning/custom-scope.md`, etc.

---

## Companion VS Code Extension

This engine has a companion VS Code extension:  
https://github.com/scottcm/aiwf-vscode-extension

**Division of Responsibilities:**
- **Engine** — All workflow orchestration, AI provider integration, state persistence  
- **Extension** — UI/UX layer, command surface, editor integration  

The extension communicates with the engine exclusively through its CLI interface following the contract defined in `API-CONTRACT.md`.

---

## Development Database (Postgres via Docker)

This project includes a small, realistic PostgreSQL schema to test AI-generated
code (especially for the `jpa-mt` profile’s domain layer: entities + repositories)
against a real multi-tenant database.

The database is provided via Docker and lives under `docker/postgres/`.

### Starting the database

From the project root:

    cd docker/postgres
    docker compose up -d

This will:

- Start a PostgreSQL 16 container
- Create the `aiwf_test` database
- Run `db/init/01-schema.sql` to create schemas, tables, RLS, and triggers
- Run `db/init/02-seed.sql` to insert sample tenants, tiers, and products

### Stopping and resetting

To stop the database **without** deleting data:

    cd docker/postgres
    docker compose down

To stop the database **and delete all data** (fresh re-init on next start):

    cd docker/postgres
    docker compose down -v

On the next `docker compose up -d`, the initialization scripts will rerun and
recreate the schema + seed data from scratch.

### Connection details

- Host: `localhost`
- Port: `5432`
- Database: `aiwf_test`
- User: `aiwf_user`
- Password: `aiwf_pass`

See `docker/postgres/README.md` for a full description of the schema, RLS
behavior, and seed data.

---

## Development Setup

```bash
# Clone repository
git clone https://github.com/scottcm/ai-workflow-engine.git
cd ai-workflow-engine

# Install dependencies with Poetry
poetry install

# Activate virtual environment
poetry shell

# Set environment variables
export STANDARDS_DIR="/path/to/your/standards"
export ARTIFACT_ROOT="/path/to/your/artifacts"

# Run tests (when available)
pytest

# Validate profile configuration
python -c "from aiwf.domain.profiles import ProfileFactory; ProfileFactory.load('jpa-mt')"
```

---

## License

MIT License

---

## Support

- **GitHub Issues:** https://github.com/scottcm/ai-workflow-engine/issues
- **Discussions:** https://github.com/scottcm/ai-workflow-engine/discussions
- **Extension Issues:** https://github.com/scottcm/aiwf-vscode-extension/issues

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
- [Configuration](#configuration)
  - [Configuration file locations](#configuration-file-locations)
  - [Getting started](#getting-started)
  - [Example configuration](#example-configuration)
  - [Configuration options](#configuration-options)
    - [`profile`](#profile)
    - [`providers`](#providers)
    - [`dev`](#dev)
  - [Precedence summary](#precedence-summary)
  - [Notes](#notes)
- [CLI Overview](#cli-overview)
- [Configuration](#configuration)
- [Standards Management](#standards-management)
- [Security](#security)
- [Documentation](#documentation)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Project Goals](#project-goals)
- [Extending the Engine](#extending-the-engine)
- [Companion VS Code Extension](#companion-vs-code-extension)
- [Development Database (Postgres via Docker)](#development-database-postgres-via-docker)
- [Development Setup](#development-setup)
- [License](#license)
- [Support](#support)

---

## Overview

The AI Workflow Engine orchestrates multi-phase code generation workflows across multiple AI providers.

It currently supports **human-in-the-loop workflows** using manual helper scripts, with automation and orchestration planned in later milestones.

---

## What This Project Demonstrates

- Deliberate application of enterprise design patterns
- Layered architecture with explicit domain boundaries
- Profile-driven extensibility
- Stateful, resumable workflows
- Manual-first design that supports later automation
- Security-conscious handling of filesystem and inputs

---

## The Problem It Solves

AI-assisted development often requires structured, repeatable workflows involving planning, generation, review, and revision. Ad-hoc approaches frequently lack:

- explicit workflow state,
- resumability,
- auditability,
- or clean separation between domain logic and tooling.

This project models those concerns explicitly.

---

## Why This Approach?

- **Budget reality**: Works with consumer AI subscriptions and manual workflows
- **Real-world complexity**: Built to support multi-tenant SaaS generation patterns
- **Auditability**: Every prompt, response, and iteration is preserved
- **Extensibility**: New domains are added via profiles, not core changes

---

## Architecture Overview

    Scripts / Future CLI
            ↓
    Application Services (planned)
            ↓
    Domain Layer (immutable generation logic)
            ↓
    Infrastructure (filesystem, AI providers, helpers)

### Key Patterns

- **Strategy** — Swap AI providers and workflow profiles at runtime  
- **Factory** — Instantiate providers and profiles from configuration  
- **Chain of Responsibility** — Compose workflow phases as a pipeline  
- **Builder** — Fluent, safe construction of handler chains  
- **Command** — Encapsulate operations such as prompt prep and bundle extraction  
- **Adapter** — Integrate CLI tools and legacy scripts behind stable interfaces  
- **Template Method** — Shared prompt skeletons with overridable sections

Detailed rationale is documented in the ADRs.

---

## Language and Framework Agnostic

The engine core is language-agnostic. Profiles encapsulate all language- and framework-specific logic.

**Current profile:**
- `jpa-mt` — Java / Spring Data JPA (multi-tenant)

---

## Profile System

Profiles define:
- standards selection
- prompt templates
- bundle extraction rules
- file writing behavior

### JPA Multi-Tenant Profile (`jpa-mt`)

Target stack:
- Java 21
- Spring Data JPA
- PostgreSQL (multi-tenant, RLS)

Supported scopes:
1. **`domain`** — Entity + Repository only
   - Generates: JPA Entity, Spring Data Repository
   - Use case: Domain layer for existing applications

2. **`vertical`** — Complete feature implementation
   - Generates: Entity → Repository → Service → Controller + DTOs/Mappers
   - Use case: Full-stack feature implementation

---

## Session Workflow

### Directory Structure

**Session directory**
```
.aiwf/sessions/{session-id}/
├── session.json
├── iteration-1/
│   ├── generation-response.md
│   └── code/
└── iteration-2/
```

### Target directory (if configured)

An optional output location where generated artifacts may be copied or projected
from the session directory for integration into an external codebase.  
The session directory remains the authoritative source of workflow state.

<target-path>/
├── domain/
├── service/
└── repository/


### Workflow Phases

1. **Planning** — Design entity structure and relationships
2. **Generation** — Generate code following approved plan
3. **Review** — Validate against standards and best practices
4. **Revision** — Fix issues identified in review (loops until pass)

These are not implementation phases.

---

Below is a **drop-in README snippet** that matches your M6 behavior exactly and explains config without overpromising.

---

## Configuration

AIWF is configured using a YAML file. Configuration can be defined at two levels, with clear precedence.

### Configuration file locations (highest wins)

1. **Project-specific**

   ```
   <project-root>/.aiwf/config.yml
   ```

2. **User-wide**

   ```
   ~/.aiwf/config.yml
   ```

Project configuration overrides user-wide configuration.
Command-line flags override both.

> The `.aiwf/` directory is intentionally ignored by Git.
> Use the provided example file as a template.

---

### Getting started

Copy the example configuration into your project:

```bash
mkdir -p .aiwf
cp docs/config/config.yml.example .aiwf/config.yml
```

Edit `.aiwf/config.yml` as needed.

---

### Example configuration

```yaml
profile: default

providers:
  planner: manual
  generator: manual
  reviewer: manual
  reviser: manual

dev: null
```

---

### Configuration options

#### `profile`

Logical workflow profile to use.

* **M6 supported values:** `default`

#### `providers`

Selects which provider is used for each workflow role.

Supported values in M6:

* `manual` — human-in-the-loop workflow using prompt/response files

Each role is configured independently:

* `planner`
* `generator`
* `reviewer`
* `reviser`

Missing roles fall back to defaults.

#### `dev`

Optional developer flag passed through to the engine.

* Set to `null` to disable
* Overridden by the `--dev` CLI flag

---

### Precedence summary

```
CLI flags
  > project .aiwf/config.yml
    > user ~/.aiwf/config.yml
      > built-in defaults
```

---

### Notes

* Configuration is read only during `aiwf init`.
* `aiwf step` and `aiwf status` do not consult configuration.

---

## Environment Variables

The engine relies on the following environment variables for filesystem boundaries
and artifact management. These variables may be configured via the operating system,
IDE run configuration, or CI environment.

- `STANDARDS_DIR`  
  Path to the root directory containing AI-optimized standards documents
  (e.g., architecture, coding standards, profile-specific rules).
  If not set, a default standards location within the repository is used.

- `ARTIFACT_ROOT`  
  Root directory where generated artifacts and workflow session data are written.
  This directory contains session subdirectories and iteration outputs.
  If not set, a default artifact location within the repository is used.

---

## CLI Overview

A full CLI is **planned**.

Current interaction is via:
- `scripts/render_prompts_manual.py`
- `scripts/extract_code_manual.py`

These scripts act as manual helpers and intentionally avoid orchestration logic.

## Planned CLI Interface

The following commands define the intended public interface of the engine.
Not all commands are implemented yet.

aiwf new
aiwf run
aiwf step
aiwf resume
aiwf status
aiwf profiles

See `API-CONTRACT.md` for complete CLI specification.

---

## Configuration

Configuration in the AI Workflow Engine is intentionally explicit and filesystem-based.

Key configuration concepts include:
- environment-defined filesystem boundaries (e.g., standards and artifact roots),
- profile selection and profile-specific rules,
- standards bundles assembled per session,
- scope selection (domain vs vertical).

Detailed configuration rules and formats are documented in the specifications
and profile documentation.


---

## Standards Management

### Immutability

Standards are bundled once at session creation and **cannot change** during the workflow. This prevents corruption from mid-session standards updates.

Detailed bundling and validation rules are defined in the specifications and enforced by tests.

---

## Security

Security considerations are addressed through explicit architectural constraints
rather than implicit trust or convention.

Key guarantees include:
- Explicit filesystem boundaries for standards, artifacts, and sessions
- Path traversal prevention when extracting and writing generated files
- Session-level isolation of workflow state and artifacts
- Immutable inputs (standards, prior iterations) to prevent mid-workflow corruption

Non-goals:
- This project does not attempt to sandbox AI-generated code
- It is not designed as a multi-user, adversarial system
- Security hardening beyond filesystem safety is deferred to downstream integration


---

## Documentation

**Architecture:**
- Architecture Decision Records under `docs/adr/`
- API contract for planned CLI
- Profile-specific documentation

**API:**
- `API-CONTRACT.md` — CLI interface specification

---

## Tech Stack

### Current

- **Python 3**
- **pytest**
- **argparse**
- **Poetry**

### Planned

- **Pydantic** — workflow state validation (Milestone M5)
- **Click** — production CLI (Milestone M6)

---

## Project Structure

```
ai-workflow-engine/
├── aiwf/
│   └── domain/
├── profiles/
│   └── jpa_mt/
├── scripts/         # Manual, human-in-the-loop helpers
├── tests/
│   ├── unit/
│   └── conftest.py
├── docs/
│   ├── adr/
│   ├── enhancements
│   ├── samples       # Sample standards
│   └── roadmap.md
└── README.md
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

The engine is designed to be extended without modifying core domain logic.
Some extension points are implemented today; others are planned and documented
to establish a stable architectural direction.

### Adding New Profiles

Profiles encapsulate language-, framework-, and domain-specific generation rules.
New profiles can be added by implementing the required profile interfaces and
registering them with the engine.

### Adding New AI Providers

AI providers are intended to be replaceable execution backends.
New providers can be integrated without changing the core workflow model.

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

The development database is provided to support validation of generated
database artifacts (e.g., JPA entities, schema mappings, and migrations).

It is intended for local development and testing only and is not required
to run the core workflow engine.

Database startup and configuration details are defined in the Docker
configuration under `docs/` and are intentionally kept out of this README.

---

## Development Setup

```bash
poetry install
pytest
```

---

## License

MIT

---

## Support

See GitHub issues and discussions.

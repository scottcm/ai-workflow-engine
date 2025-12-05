# AI Workflow Engine

**A portfolio project demonstrating enterprise architecture patterns in an AI-assisted development workflow engine**

> ⚠️ **Project Status: Active Development (Phase 1 – Foundation)**  
> A production workflow engine demonstrating enterprise architecture patterns
Built to orchestrate AI-assisted code generation for a multi-tenant SaaS application. Designed around budget constraints (works with consumer AI subscriptions), real architectural complexity (multi-tenant patterns, state management), and tight timelines.
The architecture deliberately demonstrates Strategy, Factory, Chain of Responsibility, Builder, Command, Adapter, and Template Method patterns - not because patterns are the goal, but because they solve real extensibility, testability, and maintainability challenges in this domain.

---

## Overview

The AI Workflow Engine orchestrates multi-phase code generation workflows across multiple AI providers.  
It supports both:

- **Interactive mode** – generates prompt files for manual use with web UIs  
- **Automated mode** – executes workflows using local CLI agents

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
  JSON-based workflow state with checkpoints
- **Dual execution modes**  
  Manual (prompt/paste) and automated (CLI provider calls)
- **Language-agnostic design**  
  Core engine supports any target language through profiles

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

The AI Workflow Engine addresses these issues by:

- Modeling workflows as a **phase pipeline** using Chain of Responsibility  
- Allowing different AI providers to be assigned to different roles  
- Supporting both fully automated and partially manual execution modes  
- Encapsulating domain-specific behavior in **profiles** rather than in core logic

---

## Why This Approach?

**Budget Reality**: Many startups can't afford pay-as-you-go AI APIs. This engine works with:
- Consumer subscription products (ChatGPT, Claude Pro, Gemini Advanced)
- Local CLI agents (claude, gemini)
- Manual copy-paste workflows

**Collaboration Ready**: Designed with clear contracts for a VS Code extension developer to build against.

**Real-World Use**: Built to drive actual code generation with multi-tenant patterns for a SaaS application.

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

- **Strategy** – Swap AI providers and workflow profiles at runtime  
- **Factory** – Instantiate providers and profiles from configuration  
- **Chain of Responsibility** – Compose workflow phases as a pipeline  
- **Builder** – Fluent, safe construction of handler chains  
- **Command** – Encapsulate operations such as prompt prep and bundle extraction  
- **Adapter** – Integrate CLI tools and legacy scripts behind stable interfaces  
- **Template Method** – Shared prompt skeletons with overridable sections  

Full explanations are available in the ADRs.

---

## Language and Framework Agnostic

The engine core is **language-agnostic**. Profiles encapsulate all language and framework-specific logic:

**Current Profiles:**
- Java/Spring Data JPA profiles (multi-tenant patterns)

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

### Current Profiles

**`jpa-mt-domain`** – Multi-tenant JPA domain layer generation
- **Target Stack:** Java 21, Spring Data JPA, PostgreSQL
- **Generates:** Entity + Repository with tenant isolation
- **Tenancy:** Multi-tenant with row-level security patterns
- **Standards:** JPA, database, entity, repository, naming conventions
- **Use Case:** SaaS applications requiring tenant data isolation

### Planned Profiles

**`jpa-mt-vertical`** – Multi-tenant full-stack generation
- **Target Stack:** Java 21, Spring Boot, PostgreSQL
- **Generates:** Entity → Repository → Service → Controller → DTOs
- **Tenancy:** Multi-tenant throughout the stack
- **Standards:** Full-stack including API, DTOs, service layer patterns

### First Implementation: `jpa-mt-domain`

We're starting with a Java/Spring Data JPA profile because:
1. Demonstrates real-world complexity (multi-tenancy, RLS)
2. Matches actual production use case
3. Java's verbosity showcases code generation value
4. Multi-tenant patterns are common in enterprise SaaS

The same architectural patterns apply to other languages/ORMs through additional profiles.

### Profile Architecture

Profiles are self-contained and define:
- **Prompt templates** – How to structure AI requests
- **Standards bundles** – Domain-specific coding standards
- **Validation rules** – What to check in generated code
- **Workflow phases** – Planning, generation, review, revision sequences

**Key Design Decision:** Standards selection and bundling is a **profile responsibility**, not an engine concern. This allows different profiles to use different approaches:
- Static file concatenation
- Tag-based dynamic selection
- Template-based assembly
- External tool invocation

See `docs/creating-profiles.md` for guidance on creating custom profiles.

---

## Current Implementation Status

- [x] Architecture defined and documented (ADR-0001)
- [ ] Core models (WorkflowState, Artifact)
- [ ] Provider and Profile interfaces
- [ ] `jpa-mt-domain` profile (first concrete profile)
- [ ] Handler chain and builder
- [ ] CLI interface

See documentation:

- docs/adr/0001-architecture-overview.md

---

## CLI Overview (Planned)

The engine exposes four primary CLI commands:

1. **aiwf new**  
   Initializes a workflow session without running any phases.

2. **aiwf run**  
   Creates a session and executes either the full workflow or all phases applicable in the current mode.

3. **aiwf step <phase>**  
   Runs an individual workflow phase (interactive mode only).

4. **aiwf resume**  
   Continues a previously-started workflow session.

---

## Example CLI Usage (Planned)

These commands illustrate the intended interface once the engine is fully implemented.

```bash
# Initialize a multi-tenant domain workflow
aiwf run --profile jpa-mt-domain --entity Product

# Resume from a checkpoint
aiwf resume <session-id>

# Run a single phase (interactive mode)
aiwf step generate --session <session-id>

# Generate full vertical slice (when profile available)
aiwf run --profile jpa-mt-vertical --feature OrderProcessing
```

---

## Standards Management

The engine provides reference tools and patterns for standards management, but profiles control implementation.

### Reference Implementation

`example-tools/select_standards.py` demonstrates:
- Metadata tagging of standards files
- Tag-based selection rules
- Bundle generation for AI consumption
- Critical section extraction

### Profile Integration

Profiles determine their own standards approach:

```python
class JpaMtDomainProfile(Profile):
    def prepare_standards_bundle(self, context: dict) -> str:
        """
        This profile uses tag-based selection.
        Others might use static files or different approaches.
        """
        return self._select_and_bundle_standards(
            required_tags=["jpa", "entity", "repository", "naming"],
            context=context
        )
```

See `docs/creating-profiles.md` for standards management patterns.

---

## Documentation

- **Architecture & ADRs**  
  - docs/adr/0001-architecture-overview.md
- **Creating Custom Profiles**  
  - docs/creating-profiles.md
- **Standards Management Patterns**  
  - docs/standards-patterns.md
- **Design Patterns Justification**  
  - docs/patterns.md
- **CLI API Contract**  
  - API-CONTRACT.md

Additional design rationale and commentary are available in GitHub Discussions under:

- Architecture  
- ADRs  
- Profiles & Workflows

---

## Tech Stack

- Python 3.11+
- Pydantic (data modeling and validation)
- Click (CLI interface)
- asyncio (asynchronous execution)
- pytest (testing)

---

## Project Structure

```
ai-workflow-engine/
├─ aiwf/                        # Engine core
│   ├─ domain/                  # Models, interfaces, patterns
│   ├─ application/             # Services, orchestration
│   ├─ infrastructure/          # Providers, adapters
│   └─ interface/               # CLI commands
├─ profiles/                    # Profile implementations
│   └─ jpa-mt-domain/           # First profile
│       ├─ profile.py           # Profile implementation
│       ├─ templates/           # Prompt templates
│       ├─ standards/           # Generic standards files
│       └─ README.md            # Profile documentation
├─ example-tools/               # Reference implementations
│   └─ select_standards.py      # Standards selection pattern
├─ docs/
│   ├─ adr/                     # Architecture Decision Records
│   ├─ creating-profiles.md     # Profile development guide
│   └─ standards-patterns.md    # Standards management patterns
└─ tests/
```

---

## Project Goals

This project is intentionally built to demonstrate:

1. Thoughtful, enterprise-grade architectural decisions  
2. Appropriate and justified use of design patterns  
3. Clean, maintainable code aligned with SOLID principles  
4. Comprehensive documentation (ADRs and Discussions)  
5. Extensibility for additional workflows and providers  
6. A stable integration surface for a VS Code extension and other tools
7. Language-agnostic design allowing profiles for any tech stack

---

## Extending the Engine

### Adding New Profiles

1. Create profile directory under `profiles/`
2. Implement `Profile` interface
3. Define prompt templates and standards
4. Configure validation rules and workflow phases
5. Document profile capabilities and target stack

Profiles can target any language/framework. See `docs/creating-profiles.md` for detailed guidance.

### Adding New AI Providers

1. Implement `AIProvider` interface
2. Handle provider-specific authentication and API calls
3. Register provider in factory
4. Update configuration schema

Providers are Strategy pattern implementations swapped at runtime.

---

## Companion VS Code Extension

This engine has a companion VS Code extension:  
https://github.com/scottcm/aiwf-vscode-extension

**Division of Responsibilities:**
- **Engine** – All workflow orchestration, AI provider integration, state persistence  
- **Extension** – UI/UX layer, command surface, editor integration  

The extension communicates with the engine exclusively through its CLI interface following the contract defined in `API-CONTRACT.md`.

---

## License

MIT License

# AI Workflow Engine

**A portfolio project demonstrating enterprise architecture patterns in an AI-assisted development workflow engine**

> ⚠️ **Project Status: Active Development (Phase 1 – Foundation)**  
> This project is intentionally designed to showcase clean architecture, extensibility, and advanced design patterns suitable for technical evaluation across backend, platform, and architecture-focused roles.

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
  JSON-based workflow state with checkpoints
- **Dual execution modes**  
  Manual (prompt/paste) and automated (CLI provider calls)

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

## Current Implementation Status

- [x] Architecture defined and documented (ADR-0001)
- [ ] Core models (WorkflowState, Artifact)
- [ ] Provider and Profile interfaces
- [ ] SkillsHarbor ORM profile (first concrete profile)
- [ ] Handler chain and builder
- [ ] CLI interface

See documentation:

- docs/adr/0001-architecture-overview.md

---

## CLI Overview (Planned)

The engine exposes four primary CLI commands:

1. aiwf new  
   Initializes a workflow session without running any phases.

2. aiwf run  
   Creates a session and executes either the full workflow or all phases applicable in the current mode.

3. aiwf step <phase>  
   Runs an individual workflow phase (interactive mode only).

4. aiwf resume  
   Continues a previously-started workflow session.

---

## Example CLI Usage (Planned)

These commands illustrate the intended interface once the engine is fully implemented.

    # Initialize a workflow
    aiwf run --profile skillsharbor-orm --type vertical --entity Client

    # Resume from a checkpoint
    aiwf resume <session-id>

    # Run a single phase (interactive mode)
    aiwf step generate --session <session-id>

---

## Documentation

- Architecture & ADRs  
  - docs/adr/0001-architecture-overview.md
- Design Patterns Justification (coming soon)  
  - docs/patterns.md
- Creating Custom Profiles (coming soon)  
  - docs/profiles.md

Additional design rationale and commentary are available in GitHub Discussions under:

- Architecture  
- ADRs  

---

## Tech Stack

- Python 3.11+
- Pydantic (data modeling and validation)
- Click (CLI interface)
- asyncio (asynchronous execution)
- pytest (testing)

---

## Project Goals

This project is intentionally built to demonstrate:

1. Thoughtful, enterprise-grade architectural decisions  
2. Appropriate and justified use of design patterns  
3. Clean, maintainable code aligned with SOLID principles  
4. Comprehensive documentation (ADRs and Discussions)  
5. Extensibility for additional workflows and providers  
6. A stable integration surface for a VS Code extension and other tools

---

## License

MIT License

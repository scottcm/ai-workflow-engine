# AI Workflow Engine

**A portfolio project demonstrating enterprise architecture patterns in an AI-assisted development workflow engine**

> ⚠️ **Project Status**: Active Development (Phase 1 - Foundation)  
> This is a portfolio project built to showcase clean architecture and design patterns for technical interviews.

## What This Demonstrates

- **8 Design Patterns** with clear justifications (Strategy, Chain of Responsibility, Command, Builder, Factory, Adapter, Template Method)
- **Clean Architecture** with proper layering and separation of concerns
- **Extensible Design** via profiles and dependency injection
- **State Management** with persistent, resumable workflows
- **Dual Execution Modes** (interactive manual and automated AI calls)

## The Problem It Solves

Orchestrates multi-phase AI code generation workflows:
1. Planning → 2. Generation → 3. Review → 4. Revision (loop)

Supports both **manual workflows** (paste prompts into web UIs) and **automated workflows** (direct CLI agent calls).

## Architecture Overview
```
Interface Layer (CLI)
    ↓
Application Layer (Services)  
    ↓
Domain Layer (Patterns & Core Logic)
    ↓
Infrastructure Layer (Adapters)
```

**Key Patterns**:
- **Strategy**: Swap AI providers (Claude, Gemini, etc.) and workflow profiles
- **Chain of Responsibility**: Flexible phase pipeline
- **Builder**: Fluent handler chain construction
- **Factory**: Runtime provider instantiation
- **Command**: Encapsulated operations with undo
- **Adapter**: Integrate legacy scripts and external tools
- **Template Method**: Prompt structure with overrides

## Current Implementation Status

- [x] Architecture designed and documented in ADRs
- [ ] Core models (WorkflowState, Artifact)
- [ ] Provider and Profile interfaces
- [ ] SkillsHarbor ORM profile (first concrete implementation)
- [ ] Handler chain and builder
- [ ] CLI interface

See [docs/adr/0001-architecture-overview.md](docs/adr/0001-architecture-overview.md) for complete architectural decisions.

## Quick Example (Once Implemented)
```bash
# Initialize workflow
aiwf run --profile skillsharbor-orm --type vertical --entity Client

# Resume from checkpoint
aiwf resume <session-id>

# Run single phase (interactive mode)
aiwf step generate --session <session-id>
```

## Documentation

- [ADR-0001: Architecture Overview](docs/adr/0001-architecture-overview.md)
- [Design Patterns Justification](docs/patterns.md) _(coming soon)_
- [Creating Custom Profiles](docs/profiles.md) _(coming soon)_

## Tech Stack

- Python 3.11+
- Pydantic (data validation)
- Click (CLI)
- asyncio (async execution)
- pytest (testing)

## Project Goals

This portfolio project demonstrates:
1. Enterprise-grade architecture decisions
2. Proper use of design patterns to solve real problems
3. Clean code and SOLID principles
4. Comprehensive documentation via ADRs
5. Extensible design for future requirements

**Built for**: Minneapolis job market (backend/architecture roles)  
**Timeline**: 1-month development sprint  
**Collaboration**: Designed with clear API contract for VS Code extension developer

## License

MIT License

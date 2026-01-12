# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the AI Workflow Engine.

## Current Architecture (v2.0)

**Start here:** [ADR-0001: Architecture Overview](0001-architecture-overview.md)

ADR-0001 provides the high-level architecture. ADR-0012 provides detailed design for:
- **Phase+Stage model**: PLAN, GENERATE, REVIEW, REVISE phases, each with PROMPT and RESPONSE stages
- **TransitionTable**: Declarative state machine for workflow transitions
- **Commands**: `init`, `approve`, `reject`, `status`, `list`, `validate`, `profiles`, `providers`

## V1 Archive

ADRs from v1.x that were superseded in v2.0 are preserved in the [`v1-archive/`](v1-archive/) directory for historical context. See the [v1 archive README](v1-archive/README.md) for what changed between versions.

---

## ADR Index

| ADR | Status | Title | Notes |
|-----|--------|-------|-------|
| [0001](0001-architecture-overview.md) | Accepted | Architecture Overview | **Start here** - Current architecture |
| [0003](0003-workflow-state-validation.md) | Accepted | Workflow State Validation | Pydantic for state validation |
| [0004](0004-structured-review-metadata.md) | Accepted | Structured Review Metadata | `@@@REVIEW_META` format |
| [0006](0006-observer-pattern-events-v2.md) | Accepted | Observer Pattern for Events | Event emission pattern |
| [0007](0007-plugin-architecture.md) | Accepted | Plugin Architecture | AI/Standards provider plugins |
| [0008](0008-engine-profile-separation-of-concerns.md) | Accepted | Engine-Profile Separation | Profile CLI commands, generic context |
| [0009](0009-prompt-structure-and-ai-provider-capabilities.md) | Draft | Prompt Structure | Future design - PromptBundle |
| [0010](0010-profile-provider-access.md) | Proposed | Profile Provider Access | Future - Multi-pass generation |
| [0011](0011-prompt-builder-api.md) | Draft | Prompt Builder API | PromptSections design |
| [0012](0012-workflow-phases-stages-approval-providers.md) | **Accepted** | Phases, Stages, Approval Providers | **Current architecture** |
| [0013](0013-claude-code-provider.md) | Accepted | Claude Code AI Provider | SDK-based provider |
| [0014](0014-gemini-cli-provider.md) | Accepted | Gemini CLI AI Provider | Subprocess-based provider |
| [0015](0015-approval-provider-implementation.md) | **Accepted** | Approval Provider Implementation | Approval gates system |
| [0016](0016-v2-workflow-config-and-provider-naming.md) | **Accepted** | V2 Workflow Config and Provider Naming | Provider naming convention |
| [0017](0017-plugin-dependency-injection.md) | Proposed | Plugin Dependency Injection | Future - Service registry pattern |

---

## Reading Guide

### For New Contributors

1. **[ADR-0001](0001-architecture-overview.md)** - Architecture overview (start here)
2. **[ADR-0012](0012-workflow-phases-stages-approval-providers.md)** - Phase+Stage model details
3. **[ADR-0007](0007-plugin-architecture.md)** - How providers work
4. **[ADR-0015](0015-approval-provider-implementation.md)** - Approval provider system

### For Understanding History

- **[v1-archive/](v1-archive/)** - V1 architecture decisions superseded in v2.0

### Status Definitions

| Status | Meaning |
|--------|---------|
| **Accepted** | Decision made and implemented |
| **Draft** | Design in progress, may change |
| **Proposed** | Under consideration, not started |
| **Superseded** | Replaced by a newer ADR |

---

## ADRs Needing Review

The following draft ADRs may need updates:

| ADR | Issue |
|-----|-------|
| 0009 | May overlap with ADR-0011; needs consolidation review |

---

## Creating New ADRs

Use the next available number (currently 0017). Follow the format:

```markdown
# ADR-NNNN: Title

**Status:** Draft | Proposed | Accepted | Superseded by ADR-XXXX
**Date:** YYYY-MM-DD
**Deciders:** Names

---

## Context and Problem Statement
## Decision Drivers
## Considered Options
## Decision Outcome
## Consequences
```
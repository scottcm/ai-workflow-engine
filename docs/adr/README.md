# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the AI Workflow Engine.

## Current Architecture

**Start here:** [ADR-0012: Workflow Phases, Stages, and Approval Providers](0012-workflow-phases-stages-approval-providers.md)

ADR-0012 defines the current workflow model:
- **Phase+Stage model**: PLAN, GENERATE, REVIEW, REVISE phases, each with PROMPT and RESPONSE stages
- **TransitionTable**: Declarative state machine replacing the old Chain of Responsibility pattern
- **Commands**: `init`, `step`, `approve`, `reject`, `retry`, `status`, `cancel`

The old architecture (ING/ED phases like PLANNING, PLANNED, GENERATING, GENERATED, etc.) documented in ADR-0001 has been superseded.

---

## ADR Index

| ADR | Status | Title | Notes |
|-----|--------|-------|-------|
| [0001](0001-architecture-overview.md) | Accepted | Architecture Overview | **Outdated** - Phase model superseded by ADR-0012 |
| [0002](0002-template-layering-system.md) | Accepted | Template Layering System | Valid - Profile template composition |
| [0003](0003-workflow-state-validation.md) | Accepted | Workflow State Validation | Valid - Pydantic for state validation |
| [0004](0004-structured-review-metadata.md) | Accepted | Structured Review Metadata | Valid - `@@@REVIEW_META` format |
| [0005](0005-approval-handler-chain.md) | **Superseded** | Chain of Responsibility | Replaced by TransitionTable in ADR-0012 |
| [0006](0006-observer-pattern-events-v2.md) | Accepted | Observer Pattern for Events | Valid - Event emission pattern |
| [0007](0007-plugin-architecture.md) | Accepted | Plugin Architecture | Valid - AI/Standards provider plugins |
| [0008](0008-engine-profile-separation-of-concerns.md) | Draft | Engine-Profile Separation | Partially implemented |
| [0009](0009-prompt-structure-and-ai-provider-capabilities.md) | Draft | Prompt Structure | Future design - PromptBundle |
| [0010](0010-profile-provider-access.md) | Proposed | Profile Provider Access | Future - Multi-pass generation |
| [0011](0011-prompt-builder-api.md) | Draft | Prompt Builder API | Valid - PromptSections design |
| [0012](0012-workflow-phases-stages-approval-providers.md) | **Accepted** | Phases, Stages, Approval Providers | **Current architecture** |

---

## Reading Guide

### For New Contributors

1. **[ADR-0012](0012-workflow-phases-stages-approval-providers.md)** - Current workflow model (required reading)
2. **[ADR-0007](0007-plugin-architecture.md)** - How providers work
3. **[ADR-0002](0002-template-layering-system.md)** - Profile template system

### For Understanding History

- **[ADR-0001](0001-architecture-overview.md)** - Original architecture (now partially outdated)
- **[ADR-0005](0005-approval-handler-chain.md)** - Why we tried Chain of Responsibility and replaced it

### Status Definitions

| Status | Meaning |
|--------|---------|
| **Accepted** | Decision made and implemented |
| **Draft** | Design in progress, may change |
| **Proposed** | Under consideration, not started |
| **Superseded** | Replaced by a newer ADR |

---

## ADRs Needing Updates

The following ADRs reference outdated concepts and need revision:

| ADR | Issue |
|-----|-------|
| 0001 | Documents old ING/ED phase model; needs replacement with v2 overview |
| 0004 | References "REVIEWED phase" (now `REVIEW[RESPONSE]` stage) |
| 0006 | Example code uses old phase names |
| 0007 | References ADR-0005 which is superseded |
| 0008 | Implementation plan phases may be outdated |
| 0009 | May overlap with ADR-0011; needs consolidation review |

---

## Creating New ADRs

Use the next available number (currently 0013). Follow the format:

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
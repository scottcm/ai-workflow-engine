# V1 Architecture (Archived)

These ADRs describe features implemented in v1.x that were superseded in v2.0.

## What Changed in V2

**Phase Model:**
- V1: ING/ED model (PLANNING/PLANNED, GENERATING/GENERATED, REVIEWING/REVIEWED, REVISING/REVISED)
- V2: Phase+Stage model (PLAN[PROMPT/RESPONSE], GENERATE[PROMPT/RESPONSE], REVIEW[PROMPT/RESPONSE], REVISE[PROMPT/RESPONSE])

**State Machine:**
- V1: Chain of Responsibility pattern (ADR-0005)
- V2: TransitionTable declarative state machine (ADR-0012)

**Templates:**
- V1: Layered composition with `{{include:}}` directives (ADR-0002)
- V2: Flat templates with `{{placeholder}}` substitution

**State Model:**
- V1: Profile-specific fields in WorkflowState (entity, table, scope)
- V2: Generic context dict (ADR-0008)

## Preserved ADRs

| ADR | Title | Why Archived |
|-----|-------|--------------|
| 0002 | Template Layering System | Feature unused in v2; flat templates adopted for simplicity |
| 0005 | Chain of Responsibility | Pattern replaced by TransitionTable state machine |

## V2 Architecture

See [ADR-0001: Architecture Overview](../0001-architecture-overview.md) and [ADR-0012: Phases, Stages, and Approval Providers](../0012-workflow-phases-stages-approval-providers.md) for current v2.0 architecture.
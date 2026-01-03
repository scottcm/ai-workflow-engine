# ADR-0015: Approval Provider Implementation

**Status:** Accepted
**Date:** January 2, 2025
**Deciders:** Scott

---

## Context and Problem Statement

ADR-0012 introduced the `ApprovalProvider` concept at a high level, defining the phase+stage model and approval gates. However, several implementation details were left unspecified:

1. What question is each approval gate asking?
2. How do profiles contribute domain-specific criteria without baking knowledge into approvers?
3. How should review issue validation work during revision?
4. What artifacts should be created and passed between phases?

This ADR specifies the design decisions for the approval provider system.

---

## Decision Drivers

1. **Generic Approvers** - Approvers should not contain domain knowledge; profiles provide criteria
2. **Clear Semantics** - Each approval gate should have a well-defined purpose
3. **Audit Trail** - Decisions (especially issue accept/reject) must be traceable
4. **Simplicity** - Avoid unnecessary approval gates; inline validation where possible
5. **Manual Workflow Parity** - Automated flow should mirror what users do manually

---

## Design Decisions

### 1. Approvers Are Generic

Approvers receive context but do not contain domain-specific logic. The profile contributes criteria to the context dict.

**Rationale:** Approval is orthogonal to content generation and should be independently configurable. Profiles already manage domain knowledge; approvers just evaluate.

**Rejected:** "Approval as Profile Responsibility" - Puts too much responsibility in profiles.

---

### 2. Approval Gate Semantics

Each approval gate answers a specific question. This is NOT about doing the work; it's a quality gate asking "is this ready to proceed?"

| Phase | Stage | Question Being Asked |
|-------|-------|---------------------|
| PLAN | PROMPT | "Is this planning prompt ready to send to AI?" |
| PLAN | RESPONSE | "Is this plan acceptable?" |
| GENERATE | PROMPT | "Is this generation prompt ready?" |
| GENERATE | RESPONSE | "Does this code implement the plan?" |
| REVIEW | PROMPT | "Is this review prompt ready?" |
| REVIEW | RESPONSE | "Is this review clear, actionable, and aligned with standards?" |
| REVISE | PROMPT | "Is this revision prompt ready?" |
| REVISE | RESPONSE | "Does the revision address the agreed-upon issues?" |

**Key insight:** GENERATE[RESPONSE] approval is NOT a code review. It's the gate to get to a review. The question is "did the AI implement what the plan asked for?" not "is this code good?"

---

### 3. AI Approvers Require Filesystem Access

AI approvers must have read access to the filesystem. The `files` dict contains file paths, and the approver loads content directly.

**Rationale:** Approval often requires examining large codebases and multiple files. Passing all content in context would exceed token limits and lose the ability to navigate files intelligently.

**Rejected:** API-only approvers (without FS access) - Would require engine to load all content, hitting token limits.

---

### 4. PROMPT vs RESPONSE Rejection Behavior

PROMPT and RESPONSE stages have fundamentally different rejection behaviors because they have different sources:

| Stage | Content Source | On Rejection |
|-------|---------------|--------------|
| PROMPT | Profile-generated | Cannot auto-retry (profile must regenerate or user edits) |
| RESPONSE | AI-generated | Can auto-retry (AI regenerates with feedback) |

Profiles may declare `can_regenerate_prompts` capability to enable automatic prompt regeneration on rejection.

**Rationale:** Prompts are profile-generated, not AI-generated. The retry loop (which calls AI provider) doesn't apply to prompts.

---

### 5. Manual Approval = User Command

When approver is `manual`, the orchestrator saves state and returns. The user's next command (`approve`/`reject`/`retry`) IS the approval decision.

**Rationale:** Manual approval means user provides decision via CLI command. There's no AI evaluation to perform. The orchestrator doesn't "wait" - it completes and exits.

**Rejected:** ManualApprovalProvider.evaluate() returning special value - Adds complexity; the command-based model is cleaner.

---

### 6. max_retries Exhaustion Pauses (Not ERROR)

When `retry_count > max_retries`, workflow remains IN_PROGRESS (paused) for user intervention rather than setting ERROR status.

**Rationale:** Users should review AI rejections before deciding whether to retry manually or cancel. ERROR status implies system failure, not approval disagreement. IN_PROGRESS means "waiting on user" which is semantically correct.

**Rejected:** Immediate ERROR on rejection - Too strict; loses user's ability to intervene.

---

### 7. suggested_content Is a Hint to Provider

When AI approver rejects RESPONSE with `suggested_content`, it's passed to the response provider in retry context as a hint. The approver never writes to files directly.

**Rationale:** Approvers evaluate, providers generate. Suggested content is guidance for the provider, not a directive to modify files.

**Rejected:** Approver writes to file then self-approves - Violates separation of concerns.

---

### 8. Review Issue Validation Inline with Revision

Reviews often flag false positives. Rather than adding a separate approval gate, validation happens **inline** with revision. The reviser assesses each issue, implements valid ones, and documents decisions in `revision-issues.md`.

**Rationale:** Simpler workflow (no extra approval step). Reviser has full context (code + review + plan). More powerful - reviser can explain reasoning while implementing.

**Rejected:** Separate validation phase/gate - Adds complexity without clear benefit.

---

### 9. Built-in Approval Providers

| Provider Key | Behavior |
|--------------|----------|
| `skip` | Auto-approve, no gate (workflow continues immediately) |
| `manual` | Pause workflow, require user command |
| Response provider key | Delegate to AI via `AIApprovalProvider` adapter |

---

## Configuration

Approval configuration uses existing `ApprovalConfig` infrastructure with per-stage settings:

- `approver`: Provider key (`skip`, `manual`, or response provider)
- `max_retries`: Auto-retries on rejection (AI approver only; 0 = single attempt, halt on rejection)
- `allow_rewrite`: Whether approver can suggest content changes

See implementation plan for configuration format details.

---

## Consequences

### Positive

1. **Generic approvers** - No domain knowledge required in approver code
2. **Clear semantics** - Each gate has a defined question
3. **Audit trail** - `revision-issues.md` documents all accept/reject decisions
4. **Flexible** - Profiles can customize criteria without changing approver code
5. **Manual parity** - Automated flow mirrors manual workflow

### Negative

1. **Context assembly complexity** - Engine must assemble correct files/context per gate
2. **Prompt engineering** - `AIApprovalProvider` must build effective prompts
3. **New artifact** - `revision-issues.md` adds to session file count

---

## Related Decisions

- **ADR-0012:** Phase+stage model, `ApprovalProvider` concept (this ADR extends it)
- **ADR-0013:** Claude Code provider (can be used as approver)
- **ADR-0014:** Gemini CLI provider (can be used as approver)

---

## Implementation

See [ADR-0015 Implementation Plan](../plans/adr0015-approval-providers.md) for:
- Code interfaces and snippets
- Approval prompt templates
- Files/context contract per gate
- Retry flow mechanics
- Test specifications

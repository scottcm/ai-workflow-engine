# ADR-0004: Structured Review Metadata (M4, jpa-mt)

**Status:** Accepted  
**Date:** December 13, 2024  
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine is built on the principle **"engine facilitates, human decides"**, with strong guarantees around immutability, additive iteration, and explicit user control.

In **Milestone M4 (Review & Revision Loop)**, AI-generated reviews are produced as immutable artifacts for human evaluation. These reviews are currently fully opaque to the engine and require users to open and read the full review content to determine its relevance or severity.

This creates unnecessary friction during manual triage, especially when reviews contain obvious blocking issues or are incomplete due to missing inputs.

---

## Decision Drivers

- Reduce manual friction during review triage
- Preserve immutability and human decision authority
- Maintain consistency with existing parseable AI output patterns
- Keep changes strictly within M4 scope and profile ownership
- Avoid introducing workflow control, orchestration, or state mutation

---

## Decision

For **Milestone M4**, the `jpa-mt` profile **WILL emit a small, structured metadata block** as part of AI-generated review responses.

The engine **WILL parse and display** this metadata as a **summary line in the CLI** to support fast human triage.

This metadata is **strictly informational** in M4. It **MUST NOT** influence workflow control flow, iteration handling, or persisted state.

---

## Metadata Format

Review responses for `jpa-mt` MUST include the following structured header:

```text
@@@REVIEW_META
verdict: PASS | FAIL
issues_total: <int>
issues_critical: <int>
missing_inputs: <int>
@@@
```

- All fields are required
- Integers MUST be non-negative
- All content following the metadata block is opaque to the engine

---

## Display Behavior

When metadata is successfully parsed, the engine displays a **single summary line** in the CLI:

```text
REVIEW: <verdict> | issues=<total> (critical=<critical>) | missing_inputs=<count>
```

The full review remains an immutable Markdown artifact referenced by path.

If metadata is missing or malformed, the engine displays a fallback summary indicating metadata is unavailable and continues normally.

---

## Constraints (M4)

The following constraints are mandatory for M4:

- **Display-only semantics:** Parsed metadata MUST NOT trigger automated actions or workflow decisions
- **No state mutation:** Metadata parsing and display MUST NOT modify `session.json` or any persisted state
- **Non-authoritative:** Metadata represents an AI-provided summary for human triage only
- **Graceful degradation:** Metadata absence or parse failure MUST NOT block or alter workflow progression

---

## Consequences

### Positive
- Faster human review triage
- Reduced need to open full review artifacts unnecessarily
- Preserves immutability and human decision authority
- Clean extension point for future milestones

### Negative
- Introduces metadata parsing and display logic
- Requires review templates to enforce a fixed output format

---

## Scope and Non-Goals

### In Scope
- M4 review display behavior for the `jpa-mt` profile
- Structured, parseable review metadata for summary display

### Out of Scope
- Automated workflow actions based on metadata
- Persistence of review outcomes to state
- Cross-iteration aggregation or validation
- Metadata standardization across profiles

---

## Notes

This ADR applies **only** to:
- Milestone M4
- The `jpa-mt` profile
- Review summary display behavior

Any extension of metadata semantics beyond display-only usage requires a separate ADR.

---

## Related Decisions

- ADR-0001: Architecture Overview
- ADR-0003: Workflow State Validation


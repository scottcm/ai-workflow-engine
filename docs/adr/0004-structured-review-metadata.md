# ADR-0004: Structured Review Metadata

**Status:** Accepted  
**Date:** December 13, 2024  
**Last Updated:** December 24, 2024  
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine is built on the principle **"engine facilitates, human decides"**, with strong guarantees around immutability, additive iteration, and explicit user control.

AI-generated reviews are produced as immutable artifacts for human evaluation. To support both human triage and automated workflow progression, reviews must include structured metadata that the engine can parse.

---

## Decision Drivers

- Enable workflow to progress based on review outcome (PASS → COMPLETE, FAIL → REVISING)
- Reduce manual friction during review triage
- Preserve immutability and human decision authority
- Maintain consistency with existing parseable AI output patterns
- Keep parsing logic within profile ownership

---

## Decision

The `jpa-mt` profile **emits a structured metadata block** as part of AI-generated review responses.

The engine **parses this metadata** to:
1. Display a summary line in the CLI for human triage
2. Determine workflow progression (PASS → COMPLETE, FAIL → REVISING)

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
- `verdict` determines workflow outcome
- All content following the metadata block is the full review for human consumption

---

## Workflow Integration

The profile's `process_review_response()` method parses the metadata:

| Verdict | ProcessingResult.status | Workflow Transition |
|---------|------------------------|---------------------|
| PASS | `WorkflowStatus.SUCCESS` | REVIEWED → COMPLETE |
| FAIL | `WorkflowStatus.FAILED` | REVIEWED → REVISING |

The orchestrator's `_step_reviewed()` method uses this status to advance the workflow.

---

## Display Behavior

When metadata is successfully parsed, the engine displays a summary line in the CLI:
```text
REVIEW: <verdict> | issues=<total> (critical=<critical>) | missing_inputs=<count>
```

The full review remains an immutable Markdown artifact referenced by path.

---

## Error Handling

If metadata is missing or malformed:
- `process_review_response()` returns `WorkflowStatus.ERROR`
- Workflow does not advance
- User must fix the review response file and retry

---

## Human Override

The human remains in control:
- Review response files can be edited before `approve`
- Verdict can be changed from FAIL to PASS (or vice versa) by editing the file
- `approve` captures the final state; `step` processes it

This preserves the principle: **"engine facilitates, human decides"**.

---

## Consequences

### Positive
- Automated workflow progression based on review outcome
- Faster human review triage via summary display
- Preserves immutability and human decision authority
- Clear extension point for additional metadata fields

### Negative
- Requires review templates to enforce a fixed output format
- Malformed metadata blocks progression (by design)

---

## Scope

### In Scope
- Review metadata format for the `jpa-mt` profile
- Workflow progression based on verdict
- CLI summary display

### Out of Scope
- Metadata standardization across profiles (each profile owns its format)
- Cross-iteration aggregation or validation

---

## Related Decisions

- ADR-0001: Architecture Overview
- ADR-0003: Workflow State Validation
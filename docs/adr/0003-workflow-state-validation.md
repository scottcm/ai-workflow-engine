# ADR-0003: Workflow State Validation with Pydantic

## Status
Proposed

## Context

The AI Workflow Engine relies on a durable **workflow state file** to coordinate
multi-step, AI-assisted generation workflows. This state enables:

- resuming interrupted workflows,
- validating transitions between workflow steps,
- ensuring immutability of completed steps,
- and protecting against corrupted or malformed state.

As the system evolves toward automated orchestration (Milestone M5),
the correctness of this state becomes increasingly critical. Errors in the
workflow state can lead to invalid generation steps, lost work, or undefined
behavior that is difficult to diagnose.

While the current implementation uses plain JSON-compatible structures,
there is no centralized, declarative validation mechanism that enforces
schema correctness or version compatibility.

## Decision

The project will adopt **Pydantic** for validating and serializing the
workflow state model beginning in **Milestone M5 (Orchestration Engine & State Validation)**.

Pydantic will be used to:

- define an explicit schema for workflow state,
- validate state on load and before persistence,
- surface validation errors early and clearly,
- support future schema evolution via versioned models.

This decision applies specifically to **workflow state representation** and
does not mandate Pydantic usage for other domain models unless separately decided.

## Alternatives Considered

### 1. Dataclasses with manual validation
- **Pros:** No external dependency, full control
- **Cons:** Error-prone, repetitive, validation logic easily drifts from model definition

### 2. `jsonschema`
- **Pros:** Standardized schema format, language-agnostic
- **Cons:** Less ergonomic in Python, weaker type integration, more boilerplate

### 3. No formal validation
- **Pros:** Simplicity
- **Cons:** High risk of corrupted state, poor failure diagnostics, brittle orchestration

Pydantic was selected due to its strong typing, clear error reporting,
and tight integration with Python code.

## Consequences

### Positive
- Strong guarantees around workflow state correctness
- Improved debuggability and error messages
- Clear foundation for schema versioning and migration
- Reduced cognitive load when evolving the workflow model

### Negative
- Additional dependency
- Slight runtime overhead during validation
- Requires deliberate handling of backward compatibility

These tradeoffs are acceptable given the centrality of workflow state
to system correctness.

## Scope and Non-Goals

### In Scope
- Workflow state validation and serialization
- Schema definition and versioning strategy

### Out of Scope
- CLI implementation details
- Orchestration logic itself
- Profile definitions and code generation logic
- Validation of generated source code

## Notes

This ADR supplements, but does not replace, ADR-0001.  
ADR-0001 defines architectural invariants; this ADR records a concrete
implementation decision to support those invariants.

# ADR-0016: V2 Workflow Config and Provider Naming

**Status:** Accepted
**Date:** January 4, 2026  
**Deciders:** Scott  
**Context:** Configuration and provider terminology are being revamped in v2 (breaking change).

---

## Context and Problem

V1 mixed “providers” for response generation with approval providers, used multiple config shapes, and leaned on legacy terms (“response provider”) that no longer match intent. We also need a first-class place to pass config into approval providers and to separate concerns between AI calls and approval gates. V2 can break compatibility, so we want a cohesive, phase/stage-oriented config and clear naming.

## Decision

1. **Terminology:**  
   - Rename “Response Provider” to **AI Provider** (invokes an LLM).  
   - **Approval Provider** remains a separate contract; it may delegate to an AI provider but is distinct.

2. **Config Shape (breaking):**
   - Single `workflow` block with `defaults` and per-phase/stage overrides.
   - Config follows the workflow mental model: `workflow` → `phase` → `stage` → settings.
   - Settings cascade: `defaults` → phase-level → stage-level.
   - Internally parsed into separate `AIConfig` and `ApprovalConfig` models with distinct validation.

3. **Stages (enhanced from ADR-0012):**
   - ADR-0012 configured approval per-phase; V2 allows per-stage configuration.
   - AI providers are specified only on RESPONSE stages (matching current contract).
   - Approval providers are specified on both PROMPT and RESPONSE gates, independently.
   - Terminal phases (INIT, COMPLETE, ERROR, CANCELLED) have no stages and are not configurable.

4. **Stage Settings:**
   - `ai_provider`: AI provider key; RESPONSE stages require this (via defaults or override), PROMPT stages ignore it
   - `approval_provider`: Approval provider key (`skip`, `manual`, or AI provider key)
   - `approval_max_retries`: Max auto-retries on rejection (default 0); only applies to AI approvers (`manual` returns PENDING, `skip` always approves)
   - `approval_allow_rewrite`: Whether approver can suggest content changes (default false); only applies to approvers that support rewrites (ignored for `skip`, `manual`, and approvers without rewrite capability)
   - `approver_config`: Provider-specific pass-through dict (engine doesn't interpret, just passes to provider)

5. **Factory Behavior:**
   - `ApprovalProviderFactory.create(key, config)` passes `config` into registered providers and calls optional `validate_config`.
   - Approval provider keys resolve in order: (1) registered approval providers, (2) registered AI providers wrapped via `AIApprovalProvider` adapter.
   - Keys not found in either registry fail validation at load time.
   - AI provider factory naming updated to match terminology.

6. **Validation:**
   - Loader performs a dry-run check that all configured AI/approval keys resolve.
   - Approval providers with `validate_config` fail fast on bad `approver_config`.

7. **Docs/Examples:**  
   - Config examples use the new structure and terms.  
   - Legacy shapes are removed for v2.

## New Config Structure

```yaml
workflow:
  defaults:
    ai_provider: claude-code
    approval_provider: manual
    approval_max_retries: 0
    approval_allow_rewrite: false

  plan:
    prompt:
      approval_provider: skip
    response:
      ai_provider: claude-code
      approval_provider: claude-code
      approval_max_retries: 2
      approver_config: {}   # optional

  generate:
    prompt:
      approval_provider: manual
    response:
      ai_provider: claude-code
      approval_provider: manual

  review:
    prompt:
      approval_provider: manual
    response:
      ai_provider: claude-code
      approval_provider: manual

  revise:
    prompt:
      approval_provider: manual
    response:
      ai_provider: claude-code
      approval_provider: manual
```

## Consequences

- **Breaking change:** Old config shapes and “providers” naming are not supported in v2.  
- **Clarity:** Users configure AI vs approval separately but in one cohesive block.  
- **Extensibility:** Approval providers can receive `approver_config`; validation is pluggable.  
- **Profiles:** Still own `generate_*_prompt`; they may call AI providers internally via profile-local config if desired.

## Status/Next Steps

- Implement loader/model/factory changes and update docs/tests per the accompanying implementation plan.  
- Update ADR-0015 references/examples to match terminology and config shape.

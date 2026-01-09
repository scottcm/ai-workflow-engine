# Implementation Specification Analysis

**Date:** January 6, 2026
**Scope:** All docs/plans/*.md specification files

---

## Summary

| Spec File | Status | Implementation Match |
|-----------|--------|---------------------|
| adr0007-phase1-implementation.md | COMPLETE | Fully implemented |
| adr0007-phase2-implementation.md | COMPLETE | Fully implemented |
| adr0011-implementation.md | PARTIAL | PromptSections exists but not universally used |
| adr0012_implementation.md | COMPLETE | Fully implemented |
| adr0013-claude-code-provider.md | COMPLETE | Fully implemented |
| adr0014-gemini-cli-provider.md | COMPLETE | Fully implemented |
| adr0015-approval-providers.md | COMPLETE | Fully implemented (see test-spec-analysis.md) |
| manual-approval-provider-fix.md | COMPLETE | Fully implemented |
| v2-workflow-config-implementation.md | COMPLETE | Fully implemented |
| test-spec-analysis.md | N/A | Analysis document, not a spec |

---

## Detailed Analysis

### 1. adr0007-phase1-implementation.md

**Purpose:** AI Provider invocation during workflow execution.

**Status:** COMPLETE - Implementation matches spec.

**Key deliverables:**
- `ProviderError` exception class
- `validate()` method on AIProvider
- Timeout handling in `run_provider()`
- Provider validation at init time

**Verification:** All provider tests pass. ProviderError is used throughout codebase.

---

### 2. adr0007-phase2-implementation.md

**Purpose:** Detailed provider implementation (Claude Code, Gemini CLI).

**Status:** COMPLETE - Implementation matches spec.

**Key deliverables:**
- ClaudeCodeProvider using Agent SDK
- GeminiCliProvider using subprocess
- `fs_ability` metadata
- AIProviderResult model

**Verification:** Integration tests exist for both providers. Provider factory registration works.

---

### 3. adr0011-implementation.md

**Purpose:** PromptSections model for structured prompt building.

**Status:** PARTIAL - Model exists but adoption is incomplete.

**Key deliverables:**
- PromptSections model
- Profile methods returning PromptSections or str
- Engine assembly handling both types

**Gaps identified:**
- PromptSections model exists: `aiwf/domain/models/prompt_sections.py`
- jpa-mt profile returns strings, not PromptSections
- Engine assembly supports both types but profiles haven't migrated

**Deviation:** The jpa-mt profile v2 uses YAML-based templates (`planning-prompt.yml`) instead of PromptSections. This is a valid alternative approach per D10/D13 decisions in jpa-mt-redesign.md.

**Recommendation:** Consider whether PromptSections is still needed or if the template approach supersedes it.

---

### 4. adr0012_implementation.md

**Purpose:** Phase+Stage model, TransitionTable state machine, approval providers.

**Status:** COMPLETE - Implementation matches spec.

**Key deliverables:**
- WorkflowPhase and WorkflowStage enums
- TransitionTable state machine
- ApprovalProvider ABC
- Orchestrator using TransitionTable

**Verification:**
- Phase 0 (Cleanup): Done
- Phase 1 (Models): Done - enums, ApprovalResult, stage field
- Phase 2 (State Machine): Done - TransitionTable, 68 tests
- Phase 3 (Approval Providers): Done - Skip/Manual/AI providers
- Phase 4 (Factory): Done - ApprovalProviderFactory
- Phase 5 (Orchestrator): Done - full rewrite
- Phase 6 (CLI): Done
- Phase 7 (Cleanup): Done

---

### 5. adr0013-claude-code-provider.md

**Purpose:** Claude Code provider using Agent SDK.

**Status:** COMPLETE - Implementation matches spec.

**Key features implemented:**
- Async wrapper pattern (sync interface, async SDK)
- Configuration mapping
- File extraction from messages
- Permission handling

**Verification:** `test_claude_code_provider.py` tests, integration tests available.

---

### 6. adr0014-gemini-cli-provider.md

**Purpose:** Gemini CLI provider using subprocess.

**Status:** COMPLETE - Implementation matches spec.

**Key features implemented:**
- NDJSON streaming response parsing
- Subprocess invocation
- File extraction from response
- Error handling

**Verification:** `test_gemini_cli_provider.py` tests, integration tests available.

---

### 7. adr0015-approval-providers.md

**Purpose:** Approval provider system specification.

**Status:** COMPLETE - Implementation matches spec.

**Detailed analysis:** See `test-spec-analysis.md` for full coverage analysis.

**Summary:**
- 14 spec requirements extracted
- 10 fully covered by spec tests
- 2 partially covered
- 2 gaps identified (fs_ability validation, files/context per gate)

---

### 8. manual-approval-provider-fix.md

**Purpose:** Redesign approval gate timing (gates run after content creation).

**Status:** COMPLETE - Implementation matches spec.

**Key changes implemented:**
- PENDING added to ApprovalDecision
- Gates run automatically after content creation
- `approve` command resolves PENDING (doesn't trigger gate)
- Manual approver claims `fs_ability="local-write"`
- `pending_approval` tracked in state

**Verification:** Behavioral contract tests in `test_behavioral_contracts.py`.

---

### 9. v2-workflow-config-implementation.md

**Purpose:** V2 workflow configuration and provider naming convention.

**Status:** COMPLETE - Implementation matches spec.

**Key deliverables:**
- AIProvider naming (per ADR-0016)
- ApprovalProvider naming
- AIProviderFactory and ApprovalProviderFactory
- Workflow config structure

**Verification:** All tests pass with new naming convention.

---

## Superseded Specifications

| Spec | Superseded By | Notes |
|------|---------------|-------|
| ADR-0005 | ADR-0012 | Chain of Responsibility replaced by TransitionTable |

---

## Recommendations

1. **ADR-0011 (PromptSections):** Decide whether to:
   - Migrate jpa-mt profile to PromptSections, OR
   - Document that YAML templates (D10/D13) are the preferred approach, making PromptSections optional

2. **test-spec-analysis.md gaps:** Implement the two identified gaps:
   - GAP 1: fs_ability validation in ApprovalProviderFactory
   - GAP 2: Files/context contract per gate tests

3. **Documentation cleanup:** The adr0007-phase1/phase2 implementation plans could be archived since they're fully implemented.

---

## Appendix: File Status Key

| Status | Meaning |
|--------|---------|
| COMPLETE | Spec fully implemented, matches design |
| PARTIAL | Core implemented, some gaps or deviations |
| SUPERSEDED | Replaced by newer design |
| N/A | Not an implementation spec |

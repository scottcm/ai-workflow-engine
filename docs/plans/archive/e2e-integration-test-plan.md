# E2E Integration Test Plan for jpa-mt Profile

**Status:** PLANNING
**Goal:** Verify the jpa-mt profile integrates correctly with the workflow engine across all phases

---

## Active Task

**Current Step:** Plan finalized, ready to implement
**Next Step:** Implement Phase 1 (test infrastructure)

---

## 1. What We're Testing

### Primary Goal
Verify the workflow engine correctly orchestrates the jpa-mt profile through all phases:
- INIT → PLAN → GENERATE → REVIEW → COMPLETE (happy path)
- INIT → PLAN → GENERATE → REVIEW → REVISE → REVIEW → COMPLETE (revision path)

### What Integration Tests Should Verify
1. CLI commands work (`init`, `approve`, `reject`, `status`)
2. State transitions happen correctly (phase/stage changes)
3. Files are created in correct locations (prompts, responses, artifacts)
4. **Prompt file contents** - with mocked standards, verify:
   - Entity name appears in prompt
   - Scope-appropriate rules appear (not other scopes' rules)
   - Standards bundle contains only expected rules for scope
5. Response processing extracts expected data (e.g., review verdict)

### What Integration Tests Should NOT Verify
- Prompt *quality* (that's manual review - is it a good prompt?)
- AI response *quality* (that's manual review)
- Individual profile method logic in isolation (that's unit tests)

### Unit Tests vs E2E Tests

| Aspect | Unit Test | E2E Test |
|--------|-----------|----------|
| Scope filtering | Call `_filter_by_scope()` directly | Run CLI, check `standards-bundle.md` content |
| Prompt generation | Call `generate_planning_prompt()` | Run CLI, check `planning-prompt.md` content |
| Response parsing | Call `process_review_response()` | Write mock file, run CLI, check state transition |

---

## 2. Test Paths to Cover

### All Testable Paths

There are two orthogonal dimensions:

**Content Generation (how responses are produced):**
| Mode | Mechanism | Code Path |
|------|-----------|-----------|
| Manual | `generate()` returns None → user writes file | Engine waits for file |
| AI Success | `generate()` returns AIProviderResult with content | Engine writes content |
| AI Failure | Provider raises error or returns invalid result | Engine handles error |

**Approval Gates (how content is approved):**
| Mode | Mechanism | Code Path |
|------|-----------|-----------|
| Skip | SkipApprovalProvider → always APPROVED | Auto-continue |
| Manual | ManualApprovalProvider → PENDING → user runs `approve`/`reject` | Wait for CLI |
| AI Approve | AI approver → APPROVED | Auto-continue |
| AI Reject | AI approver → REJECTED with feedback | Retry or halt |

### E2E Test Scenarios

| # | Test | Content Provider | Approval | Purpose |
|---|------|------------------|----------|---------|
| 1 | Happy path (manual) | Manual | Skip | Basic workflow, file assertions |
| 2 | Revision path (manual) | Manual | Skip | FAIL verdict → REVISE → PASS |
| 3 | Happy path (AI) | MockTestAIProvider | Skip | AI provider code path |
| 4 | AI reject + retry | MockTestAIProvider | Skip | Canned failure then success |

### Path A: Happy Path with Manual Provider
```
init → step → [PLAN/PROMPT]
     → approve → [PLAN/RESPONSE] (write mock response)
     → approve → step → [GENERATE/PROMPT]
     → approve → [GENERATE/RESPONSE] (write mock response)
     → approve → step → [REVIEW/PROMPT]
     → approve → [REVIEW/RESPONSE] (write mock PASS verdict)
     → approve → [COMPLETE]
```

### Path B: Revision Path (FAIL then PASS)
```
... same as A through REVIEW/RESPONSE ...
     → [REVIEW/RESPONSE] (write mock FAIL verdict)
     → approve → [REVISE/PROMPT]
     → approve → [REVISE/RESPONSE] (write mock response)
     → approve → step → [REVIEW/PROMPT] (iteration 2)
     → approve → [REVIEW/RESPONSE] (write mock PASS verdict)
     → approve → [COMPLETE]
```

### Path C: Happy Path with MockTestAIProvider
```
init → step → [PLAN/PROMPT]
     → approve → [PLAN/RESPONSE] (MockTestAIProvider returns canned response)
     → approve → step → [GENERATE/PROMPT]
     → approve → [GENERATE/RESPONSE] (MockTestAIProvider returns canned code)
     → approve → step → [REVIEW/PROMPT]
     → approve → [REVIEW/RESPONSE] (MockTestAIProvider returns PASS verdict)
     → approve → [COMPLETE]
```

### Path D: AI Reject + Retry
```
... same as C through GENERATE/RESPONSE ...
     → [GENERATE/RESPONSE] (MockTestAIProvider returns rejection feedback)
     → (engine auto-retries with feedback)
     → [GENERATE/RESPONSE] (MockTestAIProvider returns success on retry)
     → continue...
```

### Paths NOT Tested (unit tests or manual)
- Reject at PROMPT stage (profile regeneration - not implemented for jpa-mt)
- Multiple revision iterations
- Error conditions (malformed responses, missing files)
- AI approval gates (focus is on content generation)

---

## 3. Test Strategy Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Test framework | pytest in `tests/integration/` | Consistent with existing tests |
| CLI invocation | Real subprocess | Tests actual user experience, CLI parsing |
| Configuration | Test fixture creates temp config | Isolation, reproducibility |
| Session storage | Temp directory | Clean slate each test |
| Mock responses | Write files directly | Tests engine file reading, not AI |
| AI providers | All `manual` | No actual AI calls |
| Standards files | **Mock** (minimal rules) | Enables behavioral verification of scope filtering |
| Assertions | Check state, files, CLI output, file contents | Verify observable behavior |

### Scope Filtering Rules (IMPORTANT)

Scopes are **layer-specific**, NOT cumulative:

| Scope | Contains ONLY | Example Rules |
|-------|---------------|---------------|
| domain | Domain layer rules | `DOM-*`, `JPA-*` |
| service | Service layer rules | `SVC-*` |
| api | API layer rules | `API-*`, `CTL-*`, `DTO-*` |
| full | All rules | Everything |

Test verification: With mock rules `DOM-001`, `SVC-001`, `API-001`:
- domain scope → `standards-bundle.md` contains only `DOM-001`
- api scope → contains only `API-001`
- full scope → contains all three

---

## 4. MockTestAIProvider Design

### Purpose
Test the AI provider code path without calling real AI. Supports:
- Canned successful responses (different per phase)
- Canned rejection feedback (simulates AI rejecting content)
- Behavior changes between calls (first call fails, second succeeds)

### Interface
```python
class MockTestAIProvider(AIProvider):
    """Test-only AI provider with canned responses."""

    def __init__(self, responses: list[AIProviderResult | Exception]):
        """
        Args:
            responses: Queue of responses to return. Each call to generate()
                      pops the next response. If Exception, it's raised.
        """
        self._responses = list(responses)
        self._call_count = 0

    def generate(self, prompt: str, ...) -> AIProviderResult:
        """Return next canned response or raise next exception."""
        if not self._responses:
            raise RuntimeError("MockTestAIProvider: no more canned responses")
        response = self._responses.pop(0)
        self._call_count += 1
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def call_count(self) -> int:
        """Number of times generate() was called."""
        return self._call_count
```

### Usage in Tests
```python
# Happy path - all responses succeed
mock_provider = MockTestAIProvider([
    AIProviderResult(files={"planning-response.md": PLANNING_RESPONSE}),
    AIProviderResult(files={"generation-response.md": GENERATION_RESPONSE}),
    AIProviderResult(files={"review-response.md": REVIEW_PASS_RESPONSE}),
])

# Reject + retry - first fails, second succeeds
mock_provider = MockTestAIProvider([
    ProviderError("Validation failed: missing field"),  # First call fails
    AIProviderResult(files={"generation-response.md": FIXED_RESPONSE}),  # Retry succeeds
])
```

### Registration
```python
# In test setup, register temporarily
AIProviderFactory.register("mock-test", MockTestAIProvider)
# Config uses: ai_provider: mock-test
```

### Location
`tests/integration/mock_test_provider.py` - not in main codebase since test-only.

---

## 5. Test Implementation Plan

### Phase 1: Setup Infrastructure
- [ ] Create test fixture for temp session directory
- [ ] Create test fixture for temp config.yml with mock standards
- [ ] Create helper to run CLI commands and capture output
- [ ] Create helper to write mock response files
- [ ] Create MockTestAIProvider in `tests/integration/mock_test_provider.py`
- [ ] Create mock standards files (DOM-001, SVC-001, API-001)

### Phase 2: Happy Path Tests (Manual Provider)
- [ ] Test: `test_happy_path_init_to_complete`
  - Init session with domain scope
  - Step through all phases with mock responses (written to disk)
  - Verify COMPLETE state reached
  - Verify expected files created
  - Verify `standards-bundle.md` contains only DOM-001 (not SVC/API)

### Phase 3: Revision Path Test
- [ ] Test: `test_revision_path_fail_then_pass`
  - Same as happy path through REVIEW
  - Mock FAIL verdict
  - Verify REVISE phase entered
  - Mock revision response
  - Verify second review
  - Mock PASS verdict
  - Verify COMPLETE

### Phase 4: AI Provider Path Tests
- [ ] Test: `test_happy_path_with_mock_ai_provider`
  - Configure MockTestAIProvider with canned responses
  - Verify AI code path executes correctly
  - Verify `generate()` called expected number of times
- [ ] Test: `test_ai_provider_retry_on_failure` (stretch)
  - First `generate()` raises ProviderError
  - Engine retries, second call succeeds

### Phase 5: Edge Cases (if time permits)
- [ ] Test invalid scope
- [ ] Test missing schema file

---

## 6. Expected Results at Each Step

### After init
- `session.json` exists with phase=INIT, status=IN_PROGRESS
- `standards-bundle.md` exists
- No iteration directory yet

### After step (from INIT)
- phase=PLAN, stage=PROMPT
- `iteration-1/planning-prompt.md` exists

### After approve (PLAN/PROMPT)
- phase=PLAN, stage=RESPONSE
- Waiting for `planning-response.md`

### After writing mock response + approve
- phase=GENERATE (or next phase)
- Response file processed

### After REVIEW with PASS verdict
- phase=COMPLETE, status=SUCCESS

### After REVIEW with FAIL verdict
- phase=REVISE, stage=PROMPT
- iteration incremented

---

## 7. Mock Response Templates

### Planning Response (minimal valid)
```markdown
# Implementation Plan: {{entity}}

## Schema Analysis
- Table: {{table}}
- Columns: id, name, description

## Multi-Tenancy
- Classification: Global Reference

## Entity Design
- Fields: id, name, description

## File List
| File | Package | Class |
|------|---------|-------|
| Entity | com.example | {{entity}} |
| Repository | com.example | {{entity}}Repository |
```

### Generation Response (minimal valid)
```java
// Tier.java
@Entity
@Table(schema = "global", name = "tiers")
public class Tier {
    @Id
    private Long id;
    private String name;
}
```

### Review Response - PASS
```markdown
# Code Review

No issues found.

@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
```

### Review Response - FAIL
```markdown
# Code Review

## Issues Found
1. Missing @Column annotation

@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: 0
missing_inputs: 0
@@@
```

---

## 8. Resolved Questions

| Question | Decision | Rationale |
|----------|----------|-----------|
| CLI subprocess vs direct? | **Subprocess** | Tests real user experience, CLI parsing |
| Test file location? | `tests/integration/test_jpa_mt_e2e.py` | Simple, clear naming |
| Real or mock standards? | **Mock** | Enables verification of scope filtering behavior |

---

## 9. Open Questions

None currently - ready to implement.

---

## 10. Next Steps

1. ~~Review this plan~~ ✓
2. ~~Answer open questions~~ ✓
3. Implement Phase 1 (infrastructure)
4. Implement Phase 2 (happy path)
5. Implement Phase 3 (revision path)
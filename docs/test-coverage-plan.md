# Test Coverage Plan for Under-Tested Services

Coverage report identified 4 application services with low coverage. This document analyzes what tests are needed and recommends priorities.

## Summary

| Service | Current | Gap Analysis | Priority |
|---------|---------|--------------|----------|
| ArtifactService | 33% | Core approval logic untested | P1 |
| PromptAssembler | 26% | Variable substitution & output instructions | P2 |
| SessionFileGateway | 55% | File I/O wrapper - implicit coverage | P3 |
| PromptService | 52% | Dispatch + assembly - implicit coverage | P3 |

---

## P1: ArtifactService (33% coverage)

**Location:** `aiwf/application/artifacts/artifact_service.py`

**Why P1:** Core approval logic - hash computation, artifact creation, file extraction. Errors here affect workflow integrity.

### Current State
- No dedicated test file
- Covered indirectly via orchestrator integration tests

### Tests Needed

| Test Case | What to Verify |
|-----------|----------------|
| `test_approve_plan_response_hashes_file` | Reads planning-response.md, computes SHA256, sets plan_hash and plan_approved |
| `test_approve_plan_response_file_not_found` | Raises ValueError when response file missing |
| `test_approve_generate_response_extracts_code` | Calls profile.process_generation_response, creates artifacts for each write |
| `test_approve_generate_response_validates_paths` | PathValidator.validate_artifact_path called for each file |
| `test_approve_generate_response_no_code` | When write_plan is None, adds "no code extracted" message |
| `test_approve_review_response_hashes_file` | Reads review-response.md, sets review_hash and review_approved |
| `test_approve_revise_response_extracts_code` | Like generate but for revision-response.md |
| `test_copy_plan_to_session` | Copies planning-response.md to session-level plan.md |
| `test_copy_plan_to_session_file_not_found` | Raises ValueError when source missing |
| `test_handle_pre_transition_dispatch` | Correct handler called for each (phase, stage) key |
| `test_handle_pre_transition_no_handler` | No-op when key not in dispatch table |

### Testing Strategy
- Mock file system (or use tmp_path)
- Mock ProfileFactory.create to return a mock profile
- Inject mock add_message callback
- Verify state mutations (plan_hash, artifacts, etc.)

---

## P2: PromptAssembler (26% coverage)

**Location:** `aiwf/application/prompt_assembler.py`

**Why P2:** Engine variable substitution affects prompt correctness. Output instructions vary by fs_ability.

### Current State
- No dedicated test file
- Some coverage via PromptService tests

### Tests Needed

| Test Case | What to Verify |
|-----------|----------------|
| `test_substitute_standards_variable` | {{STANDARDS}} replaced with session_dir/standards-bundle.md |
| `test_substitute_plan_variable` | {{PLAN}} replaced with session_dir/plan.md |
| `test_output_instructions_local_write` | Full path, "Save your response to" |
| `test_output_instructions_local_read` | Filename only, "Name your output file" |
| `test_output_instructions_write_only` | Filename only, "Create a downloadable file" |
| `test_output_instructions_none` | No output instructions added |
| `test_output_instructions_no_response_path` | Empty string when response_relpath is None |
| `test_assemble_concatenates_correctly` | Profile prompt + separator + output instructions |

### Testing Strategy
- Unit tests with minimal mocking
- Verify string output contains expected substrings

---

## P3: SessionFileGateway (55% coverage)

**Location:** `aiwf/application/storage/session_file_gateway.py`

**Why P3:** Simple file I/O wrapper. Most methods are thin wrappers around Path operations. Already has implicit coverage through orchestrator tests.

### Current State
- No dedicated test file
- Heavily used by orchestrator and services

### Tests Needed (if adding any)

| Test Case | What to Verify |
|-----------|----------------|
| `test_phase_files_mapping` | PHASE_FILES contains all 4 phases with correct filenames |
| `test_ensure_iteration_dir_creates` | Creates iteration-N directory |
| `test_read_prompt_file_not_found` | Raises FileNotFoundError with path in message |
| `test_read_response_file_not_found` | Raises FileNotFoundError with path in message |
| `test_write_prompt_creates_directory` | Creates iteration dir if needed |
| `test_read_code_files_glob` | Recursively finds all files in code/ directory |

### Recommendation
**Skip for now.** This is infrastructure code with low bug risk. The integration tests exercise all paths.

---

## P3: PromptService (52% coverage)

**Location:** `aiwf/application/prompts/prompt_service.py`

**Why P3:** Dispatch logic is simple. generate_prompt is the main method; assemble_prompt is now trivial (returns input unchanged).

### Current State
- No dedicated test file
- Covered via orchestrator tests

### Tests Needed (if adding any)

| Test Case | What to Verify |
|-----------|----------------|
| `test_generate_prompt_dispatch_plan` | Calls profile.generate_planning_prompt |
| `test_generate_prompt_dispatch_generate` | Calls profile.generate_generation_prompt |
| `test_generate_prompt_unknown_phase` | Raises ValueError for INIT/COMPLETE/ERROR |
| `test_generate_prompt_returns_result` | PromptGenerationResult has user_prompt, filenames |

### Recommendation
**Skip for now.** Dispatch logic is straightforward and covered by integration tests.

---

## Recommended Action

### Decision

1. **P1 (ArtifactService)** - DO - 11 test cases
2. **P2 (PromptAssembler)** - DO - 8 test cases
3. **P3 (SessionFileGateway, PromptService)** - SKIP - adequate implicit coverage

---

## Implementation Notes

### Test File Locations
```
tests/unit/application/artifacts/test_artifact_service.py
tests/unit/application/test_prompt_assembler.py
```

### Key Fixtures Needed
```python
@pytest.fixture
def mock_profile():
    """Mock profile that returns predictable write plans."""

@pytest.fixture
def session_with_files(tmp_path):
    """Session dir with iteration-1/planning-response.md etc."""
```

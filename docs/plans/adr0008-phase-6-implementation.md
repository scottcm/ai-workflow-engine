# Phase 6: WritePlan Simplification - Implementation Guide

**Goal:** Profiles return filenames only in WritePlan; engine adds path prefix when writing.

**Dependencies:** None (can run in parallel with Phase 5)

**TDD Approach:** This phase has clear artifact writing behavior. Write tests first to specify path handling and artifact record behavior.

---

## Overview

Currently, profiles include the full path in WritePlan:
```python
WriteOp(path=f"iteration-{iteration}/code/{filename}", content=code)
```

This couples profiles to the engine's directory structure. Change to:
```python
WriteOp(path=filename, content=code)  # Just "Customer.java"
```

Engine adds the `iteration-{N}/code/` prefix when writing.

**Parallelism note:** This phase primarily modifies artifact_writer and profile response processing. If running in parallel with Phase 5 (Engine Prompt Assembly), coordinate to ensure no conflicts in workflow_orchestrator changes. Phase 5 focuses on prompt generation; this phase focuses on artifact writing.

---

## Step 1: Write Tests First

Write tests before any implementation. These tests define the expected behavior.

### 1.1 Artifact Writer Tests

**File:** `tests/unit/application/test_artifact_writer.py`

```python
"""Tests for artifact_writer with filename-only WritePlan."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from aiwf.application.artifact_writer import write_artifacts
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.write_plan import WritePlan, WriteOp
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState


@pytest.fixture
def session_dir(tmp_path):
    """Create a temporary session directory."""
    return tmp_path


@pytest.fixture
def generating_state():
    """Create a WorkflowState in GENERATING phase, iteration 1."""
    state = MagicMock(spec=WorkflowState)
    state.phase = WorkflowPhase.GENERATING
    state.current_iteration = 1
    state.artifacts = []
    return state


@pytest.fixture
def revising_state():
    """Create a WorkflowState in REVISING phase, iteration 2."""
    state = MagicMock(spec=WorkflowState)
    state.phase = WorkflowPhase.REVISING
    state.current_iteration = 2
    state.artifacts = []
    return state


class TestWriteArtifactsPathPrefix:
    """Tests for engine adding path prefix to filename-only WritePlan."""

    def test_simple_filename_gets_prefix(self, session_dir, generating_state):
        """Simple filename gets iteration-{N}/code/ prefix."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="public class Customer {}")]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        expected_path = session_dir / "iteration-1" / "code" / "Customer.java"
        assert expected_path.exists()
        assert expected_path.read_text() == "public class Customer {}"

    def test_multiple_files_all_get_prefix(self, session_dir, generating_state):
        """Multiple files all get the same prefix."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="Customer.java", content="class Customer {}"),
                    WriteOp(path="CustomerRepository.java", content="interface CustomerRepository {}"),
                ]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        code_dir = session_dir / "iteration-1" / "code"
        assert (code_dir / "Customer.java").exists()
        assert (code_dir / "CustomerRepository.java").exists()

    def test_revision_uses_current_iteration(self, session_dir, revising_state):
        """Revision phase uses current iteration (2) not previous."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="revised code")]
            )
        )

        write_artifacts(session_dir, revising_state, result)

        # Should be in iteration-2, not iteration-1
        expected_path = session_dir / "iteration-2" / "code" / "Customer.java"
        assert expected_path.exists()
        assert (session_dir / "iteration-1" / "code" / "Customer.java").exists() is False


class TestNestedPaths:
    """Tests for nested paths (subdirectories) in filenames."""

    def test_nested_path_creates_subdirectory(self, session_dir, generating_state):
        """Nested path like 'entity/Customer.java' creates subdirectory."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="entity/Customer.java", content="package entity;")]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        expected_path = session_dir / "iteration-1" / "code" / "entity" / "Customer.java"
        assert expected_path.exists()
        assert expected_path.read_text() == "package entity;"

    def test_deeply_nested_path(self, session_dir, generating_state):
        """Deeply nested paths work correctly."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[
                    WriteOp(
                        path="com/example/domain/entity/Customer.java",
                        content="package com.example.domain.entity;"
                    )
                ]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        expected_path = (
            session_dir / "iteration-1" / "code" / "com" / "example" /
            "domain" / "entity" / "Customer.java"
        )
        assert expected_path.exists()

    def test_mixed_flat_and_nested_paths(self, session_dir, generating_state):
        """Mix of flat and nested paths both work."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="README.md", content="# Readme"),
                    WriteOp(path="entity/Customer.java", content="class Customer {}"),
                    WriteOp(path="repository/CustomerRepository.java", content="interface Repo {}"),
                ]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        code_dir = session_dir / "iteration-1" / "code"
        assert (code_dir / "README.md").exists()
        assert (code_dir / "entity" / "Customer.java").exists()
        assert (code_dir / "repository" / "CustomerRepository.java").exists()


class TestArtifactRecords:
    """Tests for artifact records having full relative paths."""

    def test_artifact_record_has_full_path(self, session_dir, generating_state):
        """Artifact record contains full relative path, not just filename."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        # Check artifact record
        assert len(generating_state.artifacts) == 1
        artifact = generating_state.artifacts[0]
        assert artifact.path == "iteration-1/code/Customer.java"

    def test_nested_path_artifact_record(self, session_dir, generating_state):
        """Nested path artifact record has full path including subdirectory."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="entity/Customer.java", content="code")]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        assert len(generating_state.artifacts) == 1
        artifact = generating_state.artifacts[0]
        assert artifact.path == "iteration-1/code/entity/Customer.java"

    def test_multiple_artifacts_all_have_full_paths(self, session_dir, generating_state):
        """Multiple artifacts all have full relative paths."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="Customer.java", content="class A"),
                    WriteOp(path="entity/Order.java", content="class B"),
                ]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        assert len(generating_state.artifacts) == 2
        paths = [a.path for a in generating_state.artifacts]
        assert "iteration-1/code/Customer.java" in paths
        assert "iteration-1/code/entity/Order.java" in paths

    def test_artifact_record_includes_iteration(self, session_dir, revising_state):
        """Artifact record includes correct iteration number."""
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="revised")]
            )
        )

        write_artifacts(session_dir, revising_state, result)

        artifact = revising_state.artifacts[0]
        assert artifact.path == "iteration-2/code/Customer.java"
        assert artifact.iteration == 2


class TestEmptyWritePlan:
    """Tests for handling empty or missing WritePlan."""

    def test_no_write_plan_does_nothing(self, session_dir, generating_state):
        """No write_plan in result doesn't create files or artifacts."""
        result = ProcessingResult(write_plan=None)

        write_artifacts(session_dir, generating_state, result)

        code_dir = session_dir / "iteration-1" / "code"
        assert not code_dir.exists()
        assert len(generating_state.artifacts) == 0

    def test_empty_writes_list_does_nothing(self, session_dir, generating_state):
        """Empty writes list doesn't create files."""
        result = ProcessingResult(
            write_plan=WritePlan(writes=[])
        )

        write_artifacts(session_dir, generating_state, result)

        code_dir = session_dir / "iteration-1" / "code"
        # Directory might be created but no files
        assert len(generating_state.artifacts) == 0


class TestFileContentPreservation:
    """Tests for file content preservation."""

    def test_content_preserved_exactly(self, session_dir, generating_state):
        """File content is preserved exactly as provided."""
        content = "public class Customer {\n    private Long id;\n    // comment\n}"
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content=content)]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        written = (session_dir / "iteration-1" / "code" / "Customer.java").read_text()
        assert written == content

    def test_unicode_content_preserved(self, session_dir, generating_state):
        """Unicode content is preserved correctly."""
        content = "// Comment with émojis 🎉 and ünïcödë"
        result = ProcessingResult(
            write_plan=WritePlan(
                writes=[WriteOp(path="test.java", content=content)]
            )
        )

        write_artifacts(session_dir, generating_state, result)

        written = (session_dir / "iteration-1" / "code" / "test.java").read_text(encoding="utf-8")
        assert written == content
```

### 1.2 Profile Response Processing Tests

**File:** `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py` (add to existing)

```python
"""Tests for profile returning filenames only in WritePlan."""

import pytest
from pathlib import Path

from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile


class TestWritePlanFilenamesOnly:
    """Tests for profile returning filenames only (no iteration prefix)."""

    @pytest.fixture
    def profile(self):
        return JpaMtProfile()

    def test_generation_response_returns_filename_only(self, profile, tmp_path):
        """process_generation_response returns filename without path prefix."""
        response_content = '''
```java Customer.java
public class Customer {}
```
'''
        result = profile.process_generation_response(
            content=response_content,
            session_dir=tmp_path,
            iteration=1,
        )

        assert result.write_plan is not None
        assert len(result.write_plan.writes) == 1
        write_op = result.write_plan.writes[0]
        # Should be just filename, NOT "iteration-1/code/Customer.java"
        assert write_op.path == "Customer.java"
        assert "iteration" not in write_op.path

    def test_revision_response_returns_filename_only(self, profile, tmp_path):
        """process_revision_response returns filename without path prefix."""
        response_content = '''
```java Customer.java
public class Customer { /* revised */ }
```
'''
        result = profile.process_revision_response(
            content=response_content,
            session_dir=tmp_path,
            iteration=2,
        )

        assert result.write_plan is not None
        write_op = result.write_plan.writes[0]
        # Should be just filename, even in iteration 2
        assert write_op.path == "Customer.java"
        assert "iteration" not in write_op.path

    def test_nested_path_preserved_in_filename(self, profile, tmp_path):
        """Nested paths (e.g., entity/Customer.java) preserved in filename."""
        response_content = '''
```java entity/Customer.java
package entity;
public class Customer {}
```
'''
        result = profile.process_generation_response(
            content=response_content,
            session_dir=tmp_path,
            iteration=1,
        )

        write_op = result.write_plan.writes[0]
        # Nested path preserved but no iteration prefix
        assert write_op.path == "entity/Customer.java"
        assert "iteration" not in write_op.path
```

---

## Step 2: Implement to Pass Tests

### 2.1 Update Profile WritePlan Generation

**File:** `profiles/jpa_mt/jpa_mt_profile.py`

#### process_generation_response

Before:
```python
def process_generation_response(
    self, content: str, session_dir: Path, iteration: int
) -> ProcessingResult:
    # ...
    for filename, code in code_blocks.items():
        writes.append(WriteOp(
            path=f"iteration-{iteration}/code/{filename}",
            content=code,
        ))
```

After:
```python
def process_generation_response(
    self, content: str, session_dir: Path, iteration: int
) -> ProcessingResult:
    # ...
    for filename, code in code_blocks.items():
        writes.append(WriteOp(
            path=filename,  # Just the filename
            content=code,
        ))
```

#### process_revision_response

Same change - return filenames only.

**Note:** The `session_dir` and `iteration` parameters may no longer be needed by the profile. Consider deprecating or removing them in a future phase. For now, keep the signature for backward compatibility.

### 2.2 Update Artifact Writer

**File:** `aiwf/application/artifact_writer.py`

```python
def write_artifacts(
    session_dir: Path,
    state: WorkflowState,
    result: ProcessingResult,
) -> None:
    if not result.write_plan:
        return

    # Engine adds path prefix
    code_dir = session_dir / f"iteration-{state.current_iteration}" / "code"

    for write_op in result.write_plan.writes:
        # write_op.path is now just "filename.java" or "entity/filename.java"
        file_path = code_dir / write_op.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(write_op.content, encoding="utf-8")

        # Store full relative path in artifact record
        relative_path = f"iteration-{state.current_iteration}/code/{write_op.path}"
        state.artifacts.append(Artifact(
            path=relative_path,
            phase=state.phase,
            iteration=state.current_iteration,
            sha256=compute_hash(file_path),
        ))
```

### 2.3 Update Workflow Orchestrator References

**File:** `aiwf/application/workflow_orchestrator.py`

Check for any places that construct artifact paths and ensure they're consistent.

In `_step_generating` and `_step_revising`, the artifact path construction should remain unchanged since `write_artifacts()` now handles the prefix:

```python
# This code in orchestrator should still work:
for write_op in result.write_plan.writes:
    artifact_path = f"iteration-{state.current_iteration}/code/{write_op.path}"
    self._emit(
        WorkflowEventType.ARTIFACT_CREATED,
        state,
        artifact_path=artifact_path,
    )
```

---

## Step 3: Verify All Tests Pass

Run the test suite:

```bash
poetry run pytest tests/unit/application/test_artifact_writer.py -v
poetry run pytest tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py::TestWritePlanFilenamesOnly -v
```

All tests should pass before considering the phase complete.

---

## Testing Requirements

**File:** `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py`

1. Test `process_generation_response` returns filenames only (no `iteration-N/code/`)
2. Test `process_revision_response` returns filenames only
3. Test nested paths preserved (e.g., `entity/Customer.java`)

**File:** `tests/unit/application/test_artifact_writer.py`

4. Test `write_artifacts` adds correct path prefix
5. Test files written to `iteration-{N}/code/` directory
6. Test nested paths create correct directory structure
7. Test artifact records have full relative paths

**File:** `tests/integration/test_workflow_orchestrator.py`

8. Test end-to-end: profile returns filename, file appears in correct location
9. Test artifact events have correct paths

---

## Migration Notes

### Existing Code

The change is backward-compatible at the WritePlan interface level:
- `WriteOp.path` now contains a shorter value
- Engine code that reads `write_op.path` must add the prefix

### Legacy Behavior

If any code directly reads `write_op.path` expecting the full path, it will break. Audit for:
- Event handlers that use `write_op.path`
- Logging that displays `write_op.path`
- Tests that assert on `write_op.path` format

---

## Files Changed

| File | Change |
|------|--------|
| `profiles/jpa_mt/jpa_mt_profile.py` | Return filenames only in WritePlan |
| `aiwf/application/artifact_writer.py` | Add `iteration-{N}/code/` prefix |
| `aiwf/application/workflow_orchestrator.py` | Update event paths if needed |
| `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py` | Updated expectations |
| `tests/unit/application/test_artifact_writer.py` | New/updated tests |
| `tests/integration/test_workflow_orchestrator.py` | Updated tests |

---

## Acceptance Criteria

- [ ] Profile `process_*_response` returns filenames only (e.g., `Customer.java`)
- [ ] Files written to `session_dir/iteration-{N}/code/{filename}`
- [ ] Nested paths work correctly (e.g., `entity/Customer.java` → `iteration-1/code/entity/Customer.java`)
- [ ] Artifact records have full relative paths (e.g., `iteration-1/code/Customer.java`)
- [ ] Events emit correct full artifact paths (not just filenames)
- [ ] All tests pass
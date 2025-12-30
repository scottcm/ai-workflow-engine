import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from aiwf.application.artifact_writer import ArtifactWriteError, write_artifacts
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, ExecutionMode, WorkflowPhase, WorkflowState, WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan


def _mk_state(*, session_id: str) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        profile="jpa_mt",
        scope="domain",
        entity="Tier",
        phase=WorkflowPhase.GENERATED,
        status=WorkflowStatus.IN_PROGRESS,
        execution_mode=ExecutionMode.INTERACTIVE,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        standards_hash="sha256:deadbeef",
    )


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_write_artifacts_writes_files_in_order_and_creates_artifacts(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _mk_state(session_id="sess")
    state.current_iteration = 3
    state.phase = WorkflowPhase.GENERATED

    plan = WritePlan(
        writes=[
            WriteOp(path="iteration-3/code/A.java", content="class A {}\n"),
            WriteOp(path="iteration-3/code/B.java", content="class B {}\n"),
        ]
    )
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan)

    ret = write_artifacts(session_dir=session_dir, state=state, result=result)
    assert ret is None

    p1 = session_dir / "iteration-3/code/A.java"
    p2 = session_dir / "iteration-3/code/B.java"
    assert p1.exists()
    assert p2.exists()
    assert p1.read_text(encoding="utf-8") == "class A {}\n"
    assert p2.read_text(encoding="utf-8") == "class B {}\n"

    assert len(state.artifacts) == 2

    a1, a2 = state.artifacts
    assert isinstance(a1, Artifact)
    assert isinstance(a2, Artifact)

    # Order follows WritePlan.writes order
    assert a1.path == "iteration-3/code/A.java"
    assert a2.path == "iteration-3/code/B.java"

    assert a1.iteration == 3
    assert a2.iteration == 3
    assert a1.phase == WorkflowPhase.GENERATED
    assert a2.phase == WorkflowPhase.GENERATED

    assert a1.sha256 is None
    assert a2.sha256 is None

    assert isinstance(a1.created_at, datetime)
    assert isinstance(a2.created_at, datetime)


def test_write_artifacts_noop_when_write_plan_is_none(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _mk_state(session_id="sess")
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=None)

    ret = write_artifacts(session_dir=session_dir, state=state, result=result)
    assert ret is None

    assert state.artifacts == []
    assert list(session_dir.rglob("*")) == []


def test_write_artifacts_propagates_write_failure_and_records_no_partial_artifacts(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create a file where a directory is required to force a deterministic failure.
    conflict = session_dir / "iteration-1"
    conflict.write_text("not a directory", encoding="utf-8")

    state = _mk_state(session_id="sess")
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED

    plan = WritePlan(writes=[WriteOp(path="iteration-1/code/A.java", content="class A {}\n")])
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan)

    with pytest.raises(Exception):
        write_artifacts(session_dir=session_dir, state=state, result=result)

    # No artifacts recorded on failure
    assert state.artifacts == []

    # File should not exist (write should have failed before creating it)
    assert not (session_dir / "iteration-1/code/A.java").exists()


def test_write_artifacts_propagates_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _mk_state(session_id="sess")
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED

    plan = WritePlan(writes=[WriteOp(path="iteration-1/code/A.java", content="class A {}\n")])
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan)

    def _boom(*args, **kwargs):
        raise OSError("I/O error")

    monkeypatch.setattr(Path, "write_text", _boom)

    with pytest.raises(OSError, match="I/O error"):
        write_artifacts(session_dir=session_dir, state=state, result=result)

    assert state.artifacts == []


# === Tests for filename-only WritePlan (engine adds iteration-N/code/ prefix) ===


class TestWriteArtifactsPathPrefix:
    """Tests for engine adding path prefix to filename-only WritePlan."""

    def test_simple_filename_gets_prefix(self, tmp_path: Path):
        """Simple filename gets iteration-{N}/code/ prefix."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="public class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        expected_path = session_dir / "iteration-1" / "code" / "Customer.java"
        assert expected_path.exists()
        assert expected_path.read_text() == "public class Customer {}"

    def test_multiple_files_all_get_prefix(self, tmp_path: Path):
        """Multiple files all get the same prefix."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="Customer.java", content="class Customer {}"),
                    WriteOp(path="CustomerRepository.java", content="interface CustomerRepository {}"),
                ]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        code_dir = session_dir / "iteration-1" / "code"
        assert (code_dir / "Customer.java").exists()
        assert (code_dir / "CustomerRepository.java").exists()

    def test_revision_uses_current_iteration(self, tmp_path: Path):
        """Revision phase uses current iteration (2) not previous."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="revised code")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # Should be in iteration-2, not iteration-1
        expected_path = session_dir / "iteration-2" / "code" / "Customer.java"
        assert expected_path.exists()
        assert (session_dir / "iteration-1" / "code" / "Customer.java").exists() is False


class TestNestedPaths:
    """Tests for nested paths (subdirectories) in filenames."""

    def test_nested_path_creates_subdirectory(self, tmp_path: Path):
        """Nested path like 'entity/Customer.java' creates subdirectory."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="entity/Customer.java", content="package entity;")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        expected_path = session_dir / "iteration-1" / "code" / "entity" / "Customer.java"
        assert expected_path.exists()
        assert expected_path.read_text() == "package entity;"

    def test_deeply_nested_path(self, tmp_path: Path):
        """Deeply nested paths work correctly."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(
                        path="com/example/domain/entity/Customer.java",
                        content="package com.example.domain.entity;"
                    )
                ]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        expected_path = (
            session_dir / "iteration-1" / "code" / "com" / "example" /
            "domain" / "entity" / "Customer.java"
        )
        assert expected_path.exists()

    def test_mixed_flat_and_nested_paths(self, tmp_path: Path):
        """Mix of flat and nested paths both work."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="README.md", content="# Readme"),
                    WriteOp(path="entity/Customer.java", content="class Customer {}"),
                    WriteOp(path="repository/CustomerRepository.java", content="interface Repo {}"),
                ]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        code_dir = session_dir / "iteration-1" / "code"
        assert (code_dir / "README.md").exists()
        assert (code_dir / "entity" / "Customer.java").exists()
        assert (code_dir / "repository" / "CustomerRepository.java").exists()


class TestArtifactRecords:
    """Tests for artifact records having full relative paths."""

    def test_artifact_record_has_full_path(self, tmp_path: Path):
        """Artifact record contains full relative path, not just filename."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # Check artifact record
        assert len(state.artifacts) == 1
        artifact = state.artifacts[0]
        assert artifact.path == "iteration-1/code/Customer.java"

    def test_nested_path_artifact_record(self, tmp_path: Path):
        """Nested path artifact record has full path including subdirectory."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="entity/Customer.java", content="code")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 1
        artifact = state.artifacts[0]
        assert artifact.path == "iteration-1/code/entity/Customer.java"

    def test_multiple_artifacts_all_have_full_paths(self, tmp_path: Path):
        """Multiple artifacts all have full relative paths."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="Customer.java", content="class A"),
                    WriteOp(path="entity/Order.java", content="class B"),
                ]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 2
        paths = [a.path for a in state.artifacts]
        assert "iteration-1/code/Customer.java" in paths
        assert "iteration-1/code/entity/Order.java" in paths

    def test_artifact_record_includes_iteration(self, tmp_path: Path):
        """Artifact record includes correct iteration number."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="revised")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        artifact = state.artifacts[0]
        assert artifact.path == "iteration-2/code/Customer.java"
        assert artifact.iteration == 2


class TestEmptyWritePlanHandling:
    """Tests for handling empty or missing WritePlan."""

    def test_no_write_plan_does_nothing(self, tmp_path: Path):
        """No write_plan in result doesn't create files or artifacts."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=None)

        write_artifacts(session_dir=session_dir, state=state, result=result)

        code_dir = session_dir / "iteration-1" / "code"
        assert not code_dir.exists()
        assert len(state.artifacts) == 0

    def test_empty_writes_list_does_nothing(self, tmp_path: Path):
        """Empty writes list doesn't create files."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=[])
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # Directory might be created but no files
        assert len(state.artifacts) == 0


class TestFileContentPreservation:
    """Tests for file content preservation."""

    def test_content_preserved_exactly(self, tmp_path: Path):
        """File content is preserved exactly as provided."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        content = "public class Customer {\n    private Long id;\n    // comment\n}"
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content=content)]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        written = (session_dir / "iteration-1" / "code" / "Customer.java").read_text()
        assert written == content

    def test_unicode_content_preserved(self, tmp_path: Path):
        """Unicode content is preserved correctly."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        content = "// Comment with unicode chars"
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="test.java", content=content)]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        written = (session_dir / "iteration-1" / "code" / "test.java").read_text(encoding="utf-8")
        assert written == content


class TestProtectedFiles:
    """Tests for protected file rejection."""

    def test_session_json_rejected(self, tmp_path: Path):
        """session.json is a protected file and cannot be overwritten."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="session.json", content="malicious")]
            )
        )

        with pytest.raises(ArtifactWriteError, match="protected file"):
            write_artifacts(session_dir=session_dir, state=state, result=result)

        # File should not exist
        assert not (session_dir / "iteration-1" / "code" / "session.json").exists()
        assert len(state.artifacts) == 0

    def test_standards_bundle_rejected(self, tmp_path: Path):
        """standards-bundle.md is a protected file and cannot be overwritten."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="standards-bundle.md", content="malicious")]
            )
        )

        with pytest.raises(ArtifactWriteError, match="protected file"):
            write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0

    def test_protected_file_in_subdirectory_allowed(self, tmp_path: Path):
        """Protected filename as directory name is allowed (session.json/file.java)."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        # Directory named session.json, but filename is Customer.java
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="session.json/Customer.java", content="class Customer {}")]
            )
        )

        # This should succeed - protected check is only on filename
        write_artifacts(session_dir=session_dir, state=state, result=result)

        expected = session_dir / "iteration-1" / "code" / "session.json" / "Customer.java"
        assert expected.exists()
        assert len(state.artifacts) == 1


class TestExistingFileOverwrite:
    """Tests for preventing overwrite of existing files."""

    def test_cannot_overwrite_existing_file(self, tmp_path: Path):
        """Cannot overwrite a file that already exists (prevents accidental data loss)."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        # Pre-create the file
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        existing = code_dir / "Customer.java"
        existing.write_text("original content")

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="new content")]
            )
        )

        with pytest.raises(ArtifactWriteError, match="Cannot overwrite existing file"):
            write_artifacts(session_dir=session_dir, state=state, result=result)

        # Original content preserved
        assert existing.read_text() == "original content"
        assert len(state.artifacts) == 0

    def test_can_write_new_file_next_to_existing(self, tmp_path: Path):
        """Can write new file in directory with existing files."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        # Pre-create a different file
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        existing = code_dir / "Existing.java"
        existing.write_text("existing content")

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="NewFile.java", content="new content")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # New file created
        assert (code_dir / "NewFile.java").exists()
        assert (code_dir / "NewFile.java").read_text() == "new content"
        # Existing file untouched
        assert existing.read_text() == "existing content"
        assert len(state.artifacts) == 1


class TestPathValidationEdgeCases:
    """Tests for path validation edge cases."""

    def test_empty_path_rejected(self, tmp_path: Path):
        """Empty path is rejected."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="", content="content")]
            )
        )

        with pytest.raises(ArtifactWriteError, match="Invalid artifact path"):
            write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0

    def test_path_traversal_rejected(self, tmp_path: Path):
        """Path traversal attempts are rejected."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        traversal_paths = [
            "../Customer.java",
            "entity/../../../etc/passwd",
            "..\\Customer.java",
        ]

        for malicious_path in traversal_paths:
            result = ProcessingResult(
                status=WorkflowStatus.SUCCESS,
                write_plan=WritePlan(
                    writes=[WriteOp(path=malicious_path, content="malicious")]
                )
            )

            with pytest.raises(ArtifactWriteError, match="Invalid artifact path"):
                write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0

    def test_absolute_path_rejected(self, tmp_path: Path):
        """Absolute paths are rejected."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        absolute_paths = [
            "/etc/passwd",
            "C:\\Windows\\System32\\evil.dll",
            "\\\\server\\share\\file.txt",
        ]

        for abs_path in absolute_paths:
            result = ProcessingResult(
                status=WorkflowStatus.SUCCESS,
                write_plan=WritePlan(
                    writes=[WriteOp(path=abs_path, content="malicious")]
                )
            )

            with pytest.raises(ArtifactWriteError, match="Invalid artifact path"):
                write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0

    def test_hidden_file_rejected(self, tmp_path: Path):
        """Hidden files (starting with dot) are rejected."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        hidden_paths = [
            ".gitignore",
            ".env",
            "config/.secret",
        ]

        for hidden_path in hidden_paths:
            result = ProcessingResult(
                status=WorkflowStatus.SUCCESS,
                write_plan=WritePlan(
                    writes=[WriteOp(path=hidden_path, content="secret")]
                )
            )

            with pytest.raises(ArtifactWriteError, match="Invalid artifact path"):
                write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0

    def test_backslash_normalized_to_forward_slash(self, tmp_path: Path):
        """Windows backslashes are normalized to forward slashes."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="entity\\Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # Path should be normalized
        expected = session_dir / "iteration-1" / "code" / "entity" / "Customer.java"
        assert expected.exists()
        assert len(state.artifacts) == 1
        # Artifact path should use forward slashes
        assert state.artifacts[0].path == "iteration-1/code/entity/Customer.java"

    def test_consecutive_slashes_rejected(self, tmp_path: Path):
        """Consecutive slashes (empty segment) are rejected."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="entity//Customer.java", content="content")]
            )
        )

        with pytest.raises(ArtifactWriteError, match="Invalid artifact path"):
            write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0

    def test_trailing_slash_rejected(self, tmp_path: Path):
        """Trailing slash (empty filename) is rejected."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="entity/", content="content")]
            )
        )

        with pytest.raises(ArtifactWriteError, match="Invalid artifact path"):
            write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 0


class TestCopyForwardFromPreviousIteration:
    """Tests for copying missing files from previous iteration."""

    def test_copies_missing_files_from_previous_iteration(self, tmp_path: Path):
        """Files not in current revision are copied from previous iteration."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()

        # Create iteration-1 with two files
        iter1_code = session_dir / "iteration-1" / "code"
        iter1_code.mkdir(parents=True)
        (iter1_code / "Customer.java").write_text("class Customer {}")
        (iter1_code / "Order.java").write_text("class Order {}")

        # Now in iteration 2, profile only generates Customer.java
        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="class Customer { /*revised*/ }")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # Both files should exist in iteration-2
        iter2_code = session_dir / "iteration-2" / "code"
        assert (iter2_code / "Customer.java").exists()
        assert (iter2_code / "Order.java").exists()

        # Customer.java has new content, Order.java has copied content
        assert "revised" in (iter2_code / "Customer.java").read_text()
        assert (iter2_code / "Order.java").read_text() == "class Order {}"

        # Both should have artifact records
        assert len(state.artifacts) == 2
        paths = [a.path for a in state.artifacts]
        assert "iteration-2/code/Customer.java" in paths
        assert "iteration-2/code/Order.java" in paths

    def test_no_copy_for_iteration_1(self, tmp_path: Path):
        """Iteration 1 doesn't try to copy from non-existent iteration 0."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="class Customer {}")]
            )
        )

        # Should not raise any errors
        write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 1

    def test_copies_nested_files(self, tmp_path: Path):
        """Nested directory structure is preserved when copying."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()

        # Create iteration-1 with nested structure
        iter1_code = session_dir / "iteration-1" / "code"
        (iter1_code / "entity").mkdir(parents=True)
        (iter1_code / "repository").mkdir(parents=True)
        (iter1_code / "entity" / "Customer.java").write_text("class Customer {}")
        (iter1_code / "repository" / "CustomerRepository.java").write_text("interface CustomerRepository {}")

        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        # Profile generates just one file
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="entity/Customer.java", content="class Customer { /*revised*/ }")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        iter2_code = session_dir / "iteration-2" / "code"
        assert (iter2_code / "entity" / "Customer.java").exists()
        assert (iter2_code / "repository" / "CustomerRepository.java").exists()

        # Verify content
        assert "revised" in (iter2_code / "entity" / "Customer.java").read_text()
        assert "interface" in (iter2_code / "repository" / "CustomerRepository.java").read_text()

    def test_does_not_overwrite_new_files(self, tmp_path: Path):
        """Files written by profile are not overwritten by copy."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()

        # Create iteration-1 with a file
        iter1_code = session_dir / "iteration-1" / "code"
        iter1_code.mkdir(parents=True)
        (iter1_code / "Customer.java").write_text("OLD CONTENT")

        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        # Profile generates same file with new content
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="NEW CONTENT")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        iter2_code = session_dir / "iteration-2" / "code"
        # New content should be preserved, not overwritten by copy
        assert (iter2_code / "Customer.java").read_text() == "NEW CONTENT"

    def test_handles_missing_previous_code_dir(self, tmp_path: Path):
        """Gracefully handles case where previous iteration has no code dir."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()

        # Create iteration-1 dir but no code subdir
        (session_dir / "iteration-1").mkdir(parents=True)

        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="class Customer {}")]
            )
        )

        # Should not raise any errors
        write_artifacts(session_dir=session_dir, state=state, result=result)

        assert len(state.artifacts) == 1


class TestLegacyPrefixStripping:
    """Tests for stripping legacy iteration prefixes from profile paths."""

    def test_strips_legacy_iteration_prefix(self, tmp_path: Path):
        """Legacy 'iteration-N/' prefix is stripped and canonical prefix applied."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        # Legacy profile returns path with iteration prefix but missing /code/
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="iteration-1/Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # File should be written to canonical location
        expected = session_dir / "iteration-1" / "code" / "Customer.java"
        assert expected.exists()
        assert len(state.artifacts) == 1
        assert state.artifacts[0].path == "iteration-1/code/Customer.java"

    def test_strips_legacy_iteration_code_prefix(self, tmp_path: Path):
        """Legacy 'iteration-N/code/' prefix is stripped and canonical prefix applied."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 2
        state.phase = WorkflowPhase.REVISING

        # Legacy profile returns full path with iteration-N/code/ prefix
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="iteration-1/code/Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # File should use CURRENT iteration, not the one in the path
        expected = session_dir / "iteration-2" / "code" / "Customer.java"
        assert expected.exists()
        assert len(state.artifacts) == 1
        assert state.artifacts[0].path == "iteration-2/code/Customer.java"

    def test_strips_different_iteration_number(self, tmp_path: Path):
        """Path with different iteration number gets normalized to current iteration."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 3
        state.phase = WorkflowPhase.REVISING

        # Profile mistakenly returns path for iteration-1
        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="iteration-1/code/Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        # File should be in iteration-3, not iteration-1
        expected = session_dir / "iteration-3" / "code" / "Customer.java"
        assert expected.exists()
        assert not (session_dir / "iteration-1" / "code" / "Customer.java").exists()
        assert state.artifacts[0].path == "iteration-3/code/Customer.java"

    def test_strips_prefix_with_nested_path(self, tmp_path: Path):
        """Legacy prefix is stripped even for nested paths."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="iteration-1/code/entity/Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        expected = session_dir / "iteration-1" / "code" / "entity" / "Customer.java"
        assert expected.exists()
        assert state.artifacts[0].path == "iteration-1/code/entity/Customer.java"

    def test_filename_only_still_works(self, tmp_path: Path):
        """Filename-only paths (preferred) continue to work correctly."""
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _mk_state(session_id="sess")
        state.current_iteration = 1
        state.phase = WorkflowPhase.GENERATING

        result = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Customer.java", content="class Customer {}")]
            )
        )

        write_artifacts(session_dir=session_dir, state=state, result=result)

        expected = session_dir / "iteration-1" / "code" / "Customer.java"
        assert expected.exists()
        assert state.artifacts[0].path == "iteration-1/code/Customer.java"

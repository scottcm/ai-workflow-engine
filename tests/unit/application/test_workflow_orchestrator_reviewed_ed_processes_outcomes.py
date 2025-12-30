from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_reviewed_phase() -> None:
    assert hasattr(WorkflowPhase, "REVIEWED"), "WorkflowPhase.REVIEWED must exist for this contract"


class _StubReviewProfile:
    def __init__(self, status: WorkflowStatus, error_message: str | None = None) -> None:
        self._status = status
        self._error_message = error_message
        self.process_called = 0

    def process_review_response(self, content: str) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=self._status, error_message=self._error_message)

    def generate_revision_prompt(self, context: dict) -> str:
        """Called when REVIEWED fails and enters REVISING."""
        return "REVISION PROMPT"


def _arrange_at_reviewed(
    sessions_root: Path, utf8: str, valid_jpa_mt_context: dict[str, Any]
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)
    session_id = orch.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"primary": "gemini"},
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
    it_dir.mkdir(parents=True, exist_ok=True)
    (it_dir / "review-response.md").write_text("X", encoding=utf8)

    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.REVIEWED
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    return orch, store, session_id, it_dir


def test_reviewed_success_completes(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    stub = _StubReviewProfile(WorkflowStatus.SUCCESS)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.COMPLETE
    assert after.status == WorkflowStatus.SUCCESS
    assert stub.process_called == 1


def test_reviewed_failed_enters_revising_and_creates_next_iteration(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    stub = _StubReviewProfile(WorkflowStatus.FAILED)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert after.current_iteration == 2
    assert (sessions_root / session_id / "iteration-2").is_dir()
    assert stub.process_called == 1


def test_reviewed_error_is_recoverable_stays_in_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """When process_review_response returns ERROR, stay in REVIEWED with last_error set."""
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    error_msg = "Could not parse review metadata."
    stub = _StubReviewProfile(WorkflowStatus.ERROR, error_message=error_msg)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    # Should NOT transition to terminal ERROR phase
    assert after.phase == WorkflowPhase.REVIEWED
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert after.last_error == error_msg


def test_reviewed_success_clears_last_error(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """When process_review_response succeeds after previous error, clear last_error."""
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    # First, simulate a previous error by setting last_error
    state = store.load(session_id)
    state.last_error = "Previous error"
    store.save(state)

    stub = _StubReviewProfile(WorkflowStatus.SUCCESS)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.COMPLETE
    assert after.status == WorkflowStatus.SUCCESS
    assert after.last_error is None


def test_reviewed_cancelled_terminal_cancelled(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    stub = _StubReviewProfile(WorkflowStatus.CANCELLED)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.CANCELLED
    assert after.status == WorkflowStatus.CANCELLED


def test_reviewed_failed_does_not_copy_files_immediately(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """When review returns FAILED, code files are NOT copied immediately.

    Files are copied later by artifact_writer when processing the revision response.
    This test verifies the orchestrator does not copy files during REVIEWED -> REVISING.
    """
    _require_reviewed_phase()
    orch, store, session_id, it_dir = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    # Create code files in iteration-1 with subdirectory
    code_dir = it_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "Foo.java").write_text("class Foo {}\n", encoding=utf8)
    (code_dir / "Bar.java").write_text("class Bar {}\n", encoding=utf8)
    (code_dir / "subdir").mkdir(parents=True, exist_ok=True)
    (code_dir / "subdir" / "Baz.java").write_text("class Baz {}\n", encoding=utf8)

    stub = _StubReviewProfile(WorkflowStatus.FAILED)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    # Verify state transition
    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING
    assert after.current_iteration == 2

    # Verify iteration-2 dir exists but code files NOT copied yet
    # (copy happens in artifact_writer during REVISING -> REVISED)
    session_dir = sessions_root / session_id
    assert (session_dir / "iteration-2").is_dir()
    new_code_dir = session_dir / "iteration-2" / "code"
    assert not new_code_dir.exists()


def test_reviewed_failed_without_code_dir_still_transitions(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """When review returns FAILED but no code dir exists, transition still succeeds."""
    _require_reviewed_phase()
    orch, store, session_id, it_dir = _arrange_at_reviewed(sessions_root, utf8, valid_jpa_mt_context)

    # Ensure no code directory exists in iteration-1
    code_dir = it_dir / "code"
    assert not code_dir.exists()

    stub = _StubReviewProfile(WorkflowStatus.FAILED)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    # Verify state transition still happens
    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING
    assert after.current_iteration == 2

    # Verify new iteration dir exists but no code dir copied
    session_dir = sessions_root / session_id
    assert (session_dir / "iteration-2").is_dir()
    assert not (session_dir / "iteration-2" / "code").exists()


# Note: Tests for copy-forward behavior (copying missing files from previous iteration)
# are in test_artifact_writer.py::TestCopyForwardFromPreviousIteration since that
# functionality was moved from the orchestrator to artifact_writer.
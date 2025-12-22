from __future__ import annotations

from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_reviewed_phase() -> None:
    assert hasattr(WorkflowPhase, "REVIEWED"), "WorkflowPhase.REVIEWED must exist for this contract"


class _StubReviewProfile:
    def __init__(self, status: WorkflowStatus) -> None:
        self._status = status
        self.process_called = 0

    def process_review_response(self, content: str) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=self._status)


def _arrange_at_reviewed(
    sessions_root: Path, utf8: str
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)
    session_id = orch.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Client",
        providers={"primary": "gemini"},
        execution_mode=ExecutionMode.INTERACTIVE,
        bounded_context="client",
        table="app.clients",
        dev="test",
        task_id="LMS-000",
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
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8)

    stub = _StubReviewProfile(WorkflowStatus.SUCCESS)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.COMPLETE
    assert after.status == WorkflowStatus.SUCCESS
    assert stub.process_called == 1


def test_reviewed_failed_enters_revising_and_creates_next_iteration(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8)

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


def test_reviewed_error_terminal_error(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8)

    stub = _StubReviewProfile(WorkflowStatus.ERROR)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.ERROR
    assert after.status == WorkflowStatus.ERROR


def test_reviewed_cancelled_terminal_cancelled(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, _ = _arrange_at_reviewed(sessions_root, utf8)

    stub = _StubReviewProfile(WorkflowStatus.CANCELLED)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.CANCELLED
    assert after.status == WorkflowStatus.CANCELLED
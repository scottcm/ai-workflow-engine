from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.constants import RESPONSES_DIR
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_reviewed_phase() -> None:
    assert hasattr(WorkflowPhase, "REVIEWED"), "WorkflowPhase.REVIEWED must exist for this contract"


def _require_revised_phase() -> None:
    assert hasattr(WorkflowPhase, "REVISED"), "WorkflowPhase.REVISED must exist for this contract"


def test_generated_noop_when_generation_response_missing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    # Intentionally no generation-response.md

    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_updated_at = before.updated_at
    before_hist_len = len(before.phase_history)

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATED
    assert after.updated_at == before_updated_at
    assert len(after.phase_history) == before_hist_len


def test_reviewed_noop_when_review_response_missing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
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
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    # Intentionally no review-response.md

    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.REVIEWED
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_updated_at = before.updated_at
    before_hist_len = len(before.phase_history)

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWED
    assert after.updated_at == before_updated_at
    assert len(after.phase_history) == before_hist_len


def test_revised_noop_when_revision_response_missing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_revised_phase()
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
    it_dir = session_dir / "iteration-2"
    it_dir.mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    # Intentionally no revision-response.md

    state = store.load(session_id)
    state.current_iteration = 2
    state.phase = WorkflowPhase.REVISED
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_updated_at = before.updated_at
    before_hist_len = len(before.phase_history)

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISED
    assert after.updated_at == before_updated_at
    assert len(after.phase_history) == before_hist_len

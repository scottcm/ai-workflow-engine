from __future__ import annotations

from pathlib import Path

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore


def test_initialize_run_creates_session_and_persists_state_without_iteration_dirs(
    sessions_root: Path,
) -> None:
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orchestrator.initialize_run(
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

    state = store.load(session_id)
    assert state.session_id == session_id
    assert state.phase == WorkflowPhase.INITIALIZED
    assert state.status == WorkflowStatus.IN_PROGRESS

    session_dir = sessions_root / session_id
    assert session_dir.is_dir()
    assert not any(p.name.startswith("iteration-") for p in session_dir.iterdir())


def test_initialize_run_normalizes_windows_backslashes_in_metadata(
    sessions_root: Path,
) -> None:
    """Verify that Windows backslashes in metadata are normalized to forward slashes."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Client",
        providers={"primary": "gemini"},
        metadata={"schema_file": "docs\\samples\\schema.sql"},
    )

    state = store.load(session_id)
    assert state.metadata["schema_file"] == "docs/samples/schema.sql"

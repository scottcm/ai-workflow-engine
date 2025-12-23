from __future__ import annotations

from pathlib import Path

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore


def test_step_transitions_initialized_to_planning_only(
    sessions_root: Path,
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

    before = store.load(session_id)
    assert before.phase == WorkflowPhase.INITIALIZED

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.PLANNING
    assert after.status == WorkflowStatus.IN_PROGRESS

    # Planning prompt generated on entry to PLANNING
    session_dir = sessions_root / session_id
    assert session_dir.is_dir()
    prompt_file = session_dir / "iteration-1" / "planning-prompt.md"
    assert prompt_file.is_file()

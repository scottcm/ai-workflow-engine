from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _StubPlanningProfile:
    def __init__(self, status: WorkflowStatus = WorkflowStatus.SUCCESS, error_message: str | None = None) -> None:
        self.process_called = 0
        self._status = status
        self._error_message = error_message

    def process_planning_response(self, content: str) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=self._status, error_message=self._error_message)

    def generate_generation_prompt(self, context: dict) -> str:
        """Called on entry to GENERATING."""
        return "GENERATION PROMPT"


def test_planned_processes_planning_response_writes_plan_and_enters_generating_with_iteration_1(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )
    orch.step(session_id)  # INITIALIZED -> PLANNING

    session_dir = sessions_root / session_id

    # Planning artifacts are in iteration-1 per approval_specs.py
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (iteration_dir / "planning-response.md").write_text("# PLAN\n- x\n", encoding=utf8)

    # Also create plan.md at session root for ED approval
    (session_dir / "plan.md").write_text("# PLAN\n- x\n", encoding=utf8)

    # PLANNING -> PLANNED (no profile call needed for phase transition)
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)

    assert store.load(session_id).phase == WorkflowPhase.PLANNED

    # PLANNED requires approval before step() advances
    stub = _StubPlanningProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)  # Sets plan_approved=True, plan_hash

    state_after_approve = store.load(session_id)
    assert state_after_approve.plan_approved is True
    assert state_after_approve.plan_hash is not None

    orch.step(session_id)  # PLANNED processes response -> GENERATING

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATING
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert getattr(after, "current_iteration") == 1

    # plan promoted to session scope
    assert (session_dir / "plan.md").is_file()

    # iteration-1 allocated
    assert (session_dir / "iteration-1").is_dir()
    assert stub.process_called == 1


def test_planned_error_is_recoverable_stays_in_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """When process_planning_response returns ERROR, stay in PLANNED with last_error set."""
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )
    orch.step(session_id)  # INITIALIZED -> PLANNING

    session_dir = sessions_root / session_id
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (iteration_dir / "planning-response.md").write_text("# PLAN\n- x\n", encoding=utf8)
    (session_dir / "plan.md").write_text("# PLAN\n- x\n", encoding=utf8)

    # PLANNING -> PLANNED
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)
    assert store.load(session_id).phase == WorkflowPhase.PLANNED

    # PLANNED requires approval before step() advances
    error_msg = "Planning response is empty."
    stub = _StubPlanningProfile(status=WorkflowStatus.ERROR, error_message=error_msg)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    # Should NOT transition to terminal ERROR phase
    assert after.phase == WorkflowPhase.PLANNED
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert after.last_error == error_msg
    assert stub.process_called == 1


def test_planned_success_clears_last_error(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """When process_planning_response succeeds after previous error, clear last_error."""
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )
    orch.step(session_id)  # INITIALIZED -> PLANNING

    session_dir = sessions_root / session_id
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (iteration_dir / "planning-response.md").write_text("# PLAN\n- x\n", encoding=utf8)
    (session_dir / "plan.md").write_text("# PLAN\n- x\n", encoding=utf8)

    # PLANNING -> PLANNED
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)

    # Set up previous error
    state = store.load(session_id)
    state.last_error = "Previous error"
    store.save(state)

    # PLANNED -> GENERATING with success
    stub = _StubPlanningProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.approve(session_id)
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATING
    assert after.last_error is None
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR, PLANS_DIR
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _StubPlanningProfile:
    def __init__(self) -> None:
        self.process_called = 0

    def process_planning_response(self, content: str) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


def test_planned_processes_planning_response_writes_plan_and_enters_generating_with_iteration_1(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa_mt",
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
    orch.step(session_id)  # INITIALIZED -> PLANNING

    session_dir = sessions_root / session_id
    (session_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / PROMPTS_DIR / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (session_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / RESPONSES_DIR / "planning-response.md").write_text("# PLAN\n- x\n", encoding=utf8)

    # PLANNING -> PLANNED
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)

    assert store.load(session_id).phase == WorkflowPhase.PLANNED

    stub = _StubPlanningProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)  # PLANNED processes response -> GENERATING

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATING
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert getattr(after, "current_iteration") == 1

    # plan promoted to session scope
    assert (session_dir / PLANS_DIR / "plan.md").is_file()

    # iteration-1 allocated
    assert (session_dir / "iteration-1").is_dir()
    assert stub.process_called == 1

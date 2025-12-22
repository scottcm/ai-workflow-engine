from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _StubPlanningProfile:
    def process_planning_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


class _StubGenPromptProfile:
    def __init__(self) -> None:
        self.generate_called = 0

    def generate_generation_prompt(self, context: dict[str, Any]) -> str:
        self.generate_called += 1
        return "GENERATION PROMPT"


class _StubGenProcessProfile:
    def __init__(self) -> None:
        self.process_called = 0

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


def _arrange_at_generating(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)
    session_id = orch.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Client",
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        bounded_context="client",
        table="app.clients",
        dev="test",
        task_id="LMS-000",
        metadata={"test": True},
    )
    orch.step(session_id)  # -> PLANNING

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
    it_dir.mkdir(parents=True, exist_ok=True)
    (it_dir / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / "planning-response.md").write_text("# PLAN\n", encoding=utf8)
    
    # Create plan.md at session root for ED approval
    (session_dir / "plan.md").write_text("# PLAN\n", encoding=utf8)

    # PLANNING -> PLANNED (no profile call)
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)
    assert store.load(session_id).phase == WorkflowPhase.PLANNED

    # Approve PLANNED (required before step advances)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubPlanningProfile()))
    orch.approve(session_id)

    # PLANNED -> GENERATING
    orch.step(session_id)

    state = store.load(session_id)
    assert state.phase == WorkflowPhase.GENERATING
    assert it_dir.is_dir()
    return orch, store, session_id, it_dir


def test_generating_writes_generation_prompt_if_missing_and_stays_generating(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    stub = _StubGenPromptProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATING
    prompt_file = it_dir / "generation-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "GENERATION PROMPT"
    assert stub.generate_called == 1


def test_generating_processes_response_and_transitions_to_generated(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When response exists, GENERATING processes it and transitions to GENERATED.
    
    Note: Current implementation processes response in GENERATING (ING phase).
    This differs from ADR-0001's intended ING/ED split but matches actual implementation.
    """
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    (it_dir / "generation-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    stub = _StubGenProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATED
    assert stub.process_called == 1
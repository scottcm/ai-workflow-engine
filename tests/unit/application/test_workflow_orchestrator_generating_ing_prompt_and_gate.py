from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _StubPlanningProfile:
    def process_planning_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS)

    def generate_generation_prompt(self, context: dict) -> str:
        return "GENERATION PROMPT"


class _StubGenProcessProfile:
    def __init__(self, status: WorkflowStatus = WorkflowStatus.SUCCESS, error_message: str | None = None) -> None:
        self.process_called = 0
        self._status = status
        self._error_message = error_message

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=self._status, error_message=self._error_message)


def _arrange_at_generating(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    """Arrange state at GENERATING with prompt already generated."""
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
    orch.step(session_id)  # -> PLANNING (generates planning-prompt.md)

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
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

    # PLANNED -> GENERATING (also generates generation-prompt.md)
    orch.step(session_id)

    state = store.load(session_id)
    assert state.phase == WorkflowPhase.GENERATING
    assert it_dir.is_dir()
    return orch, store, session_id, it_dir


def test_generation_prompt_generated_on_entry_from_planned(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prompt generation now happens on entry to GENERATING (in _step_planned)."""
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    # Check that generation-prompt.md was created on entry
    prompt_file = it_dir / "generation-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "GENERATION PROMPT"


def test_generating_is_noop_when_response_missing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GENERATING phase is a no-op waiting for response (prompt already exists)."""
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    # Guard: profile must not be called in GENERATING phase when no response exists
    # (auto-approval bypass may call it but with empty content, so we allow that)
    before = store.load(session_id)
    before_hist_len = len(before.phase_history)

    orch.step(session_id)  # GENERATING - no response, stays in GENERATING

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATING
    assert len(after.phase_history) == before_hist_len


def test_generating_processes_response_and_transitions_to_generated(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When response exists, GENERATING processes it and transitions to GENERATED."""
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    # Prompt already exists from _arrange_at_generating
    (it_dir / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    stub = _StubGenProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATED
    assert stub.process_called == 1


def test_generating_error_is_recoverable_stays_in_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When process_generation_response returns ERROR, stay in GENERATING with last_error set."""
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    (it_dir / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    error_msg = "No code blocks found in generation response."
    stub = _StubGenProcessProfile(status=WorkflowStatus.ERROR, error_message=error_msg)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    # Should NOT transition to terminal ERROR phase
    assert after.phase == WorkflowPhase.GENERATING
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert after.last_error == error_msg
    assert stub.process_called == 1


def test_generating_success_clears_last_error(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When process_generation_response succeeds after previous error, clear last_error."""
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    # Set up previous error
    state = store.load(session_id)
    state.last_error = "Previous error"
    store.save(state)

    (it_dir / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    stub = _StubGenProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATED
    assert after.last_error is None

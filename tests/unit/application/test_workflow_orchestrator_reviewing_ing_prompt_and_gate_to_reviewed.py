from __future__ import annotations

from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import Artifact, ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_reviewed_phase() -> None:
    assert hasattr(WorkflowPhase, "REVIEWED"), "WorkflowPhase.REVIEWED must exist for this contract"


def _arrange_at_reviewing_with_prompt(
    sessions_root: Path, utf8: str
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    """Arrange state at REVIEWING with prompt already written (as if from GENERATED)."""
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
    # Force state to REVIEWING with iteration-1 and prompt already written
    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
    it_dir.mkdir(parents=True, exist_ok=True)

    # Simulate prompt was already generated on entry to REVIEWING
    (it_dir / "review-prompt.md").write_text("REVIEW PROMPT", encoding=utf8)

    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.REVIEWING
    store.save(state)
    return orch, store, session_id, it_dir


def test_reviewing_is_noop_when_response_missing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REVIEWING phase is a no-op waiting for response (prompt was generated on entry)."""
    _require_reviewed_phase()
    orch, store, session_id, it_dir = _arrange_at_reviewing_with_prompt(sessions_root, utf8)

    # Guard: profile must not be called in REVIEWING phase (only checks for response)
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_hist_len = len(before.phase_history)

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING
    assert len(after.phase_history) == before_hist_len


def test_reviewing_transitions_to_reviewed_when_response_exists_without_processing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, it_dir = _arrange_at_reviewing_with_prompt(sessions_root, utf8)

    # Prompt already exists from arrangement
    (it_dir / "review-response.md").write_text("VERDICT: PASS\n", encoding=utf8)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWED


class _StubReviewPromptProfile:
    def generate_review_prompt(self, context: dict) -> str:
        return "REVIEW PROMPT FROM GENERATED"


def test_review_prompt_generated_on_entry_from_generated(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review prompt is generated on entry to REVIEWING (in _step_generated)."""
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

    # Force state to GENERATED with approved artifacts
    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED
    # Add an approved artifact to pass the gate
    state.artifacts.append(Artifact(path="iteration-1/code/test.py", phase=WorkflowPhase.GENERATED, iteration=1, sha256="abc123"))
    store.save(state)

    # Stub the profile for prompt generation
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubReviewPromptProfile()))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING

    prompt_file = it_dir / "review-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "REVIEW PROMPT FROM GENERATED"

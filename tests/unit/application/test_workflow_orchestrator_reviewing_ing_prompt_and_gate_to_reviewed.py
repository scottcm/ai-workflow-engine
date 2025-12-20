from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_reviewed_phase() -> None:
    assert hasattr(WorkflowPhase, "REVIEWED"), "WorkflowPhase.REVIEWED must exist for this contract"


class _StubReviewPromptProfile:
    def __init__(self) -> None:
        self.generate_called = 0

    def generate_review_prompt(self, context: dict[str, Any]) -> str:
        self.generate_called += 1
        return "REVIEW PROMPT"


def _arrange_at_reviewing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
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
    # Force state to REVIEWING with iteration-1 existing (generation not under test here)
    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
    it_dir.mkdir(parents=True, exist_ok=True)
    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.REVIEWING
    store.save(state)
    return orch, store, session_id, it_dir


def test_reviewing_writes_review_prompt_if_missing_and_stays_reviewing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, it_dir = _arrange_at_reviewing(sessions_root, utf8, monkeypatch)

    stub = _StubReviewPromptProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING
    prompt_file = it_dir / PROMPTS_DIR / "review-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "REVIEW PROMPT"
    assert stub.generate_called == 1


def test_reviewing_transitions_to_reviewed_when_response_exists_without_processing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_reviewed_phase()
    orch, store, session_id, it_dir = _arrange_at_reviewing(sessions_root, utf8, monkeypatch)

    (it_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / PROMPTS_DIR / "review-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR / "review-response.md").write_text("VERDICT: PASS\n", encoding=utf8)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWED

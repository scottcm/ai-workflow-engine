from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR
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


def _arrange_at_generating(
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
    orch.step(session_id)  # -> PLANNING

    session_dir = sessions_root / session_id
    (session_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / PROMPTS_DIR / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (session_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / RESPONSES_DIR / "planning-response.md").write_text("# PLAN\n", encoding=utf8)

    # PLANNING -> PLANNED (no profile)
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)

    # PLANNED -> GENERATING (process planning)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubPlanningProfile()))
    orch.step(session_id)

    state = store.load(session_id)
    assert state.phase == WorkflowPhase.GENERATING
    it_dir = session_dir / "iteration-1"
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
    prompt_file = it_dir / PROMPTS_DIR / "generation-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "GENERATION PROMPT"
    assert stub.generate_called == 1


def test_generating_transitions_to_generated_when_response_exists_without_processing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_generating(sessions_root, utf8, monkeypatch)

    (it_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / PROMPTS_DIR / "generation-prompt.md").write_text("PROMPT", encoding=utf8)

    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATED

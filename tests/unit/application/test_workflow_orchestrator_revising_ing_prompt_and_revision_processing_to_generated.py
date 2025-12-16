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


class _StubRevisionPromptProfile:
    def __init__(self) -> None:
        self.generate_called = 0

    def generate_revision_prompt(self, context: dict[str, Any]) -> str:
        self.generate_called += 1
        return "REVISION PROMPT"


class _StubRevisionProcessProfile:
    def __init__(self) -> None:
        self.process_called = 0

    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


def _arrange_at_revising(
    sessions_root: Path, utf8: str
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
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
    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-2"
    it_dir.mkdir(parents=True, exist_ok=True)

    state = store.load(session_id)
    state.current_iteration = 2
    state.phase = WorkflowPhase.REVISING
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    return orch, store, session_id, it_dir


def test_revising_writes_revision_prompt_if_missing_and_stays_revising(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    stub = _StubRevisionPromptProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING

    prompt_file = it_dir / PROMPTS_DIR / "revision-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "REVISION PROMPT"
    assert stub.generate_called == 1


def test_revising_processes_revision_response_and_transitions_to_generated_on_success(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    (it_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / PROMPTS_DIR / "revision-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR / "revision-response.md").write_text("RESPONSE", encoding=utf8)

    stub = _StubRevisionProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.GENERATED
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert stub.process_called == 1

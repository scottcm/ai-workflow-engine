from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _StubPromptProfile:
    def __init__(self) -> None:
        self.generate_called = 0

    def generate_planning_prompt(self, context: dict[str, Any]) -> str:
        self.generate_called += 1
        return "PLANNING PROMPT"


def test_planning_writes_prompt_if_missing_and_stays_in_planning(
    sessions_root: Path, monkeypatch: pytest.MonkeyPatch
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

    orch.step(session_id)  # INITIALIZED -> PLANNING

    stub = _StubPromptProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    before = store.load(session_id)
    assert before.phase == WorkflowPhase.PLANNING
    before_hist_len = len(before.phase_history)

    orch.step(session_id)  # PLANNING should write prompt and stay PLANNING

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.PLANNING
    assert after.status == WorkflowStatus.IN_PROGRESS
    # prompt issuance does not advance phase
    assert len(after.phase_history) == before_hist_len

    session_dir = sessions_root / session_id
    prompt_file = session_dir / PROMPTS_DIR / "planning-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding="utf-8") == "PLANNING PROMPT"
    assert stub.generate_called == 1


def test_planning_is_noop_when_prompt_exists_and_response_missing(
    sessions_root: Path, monkeypatch: pytest.MonkeyPatch
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
    orch.step(session_id)  # INITIALIZED -> PLANNING

    session_dir = sessions_root / session_id
    (session_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / PROMPTS_DIR / "planning-prompt.md").write_text("X", encoding="utf-8")

    # Guard: profile must not be called in this no-op case
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_updated_at = before.updated_at
    before_hist_len = len(before.phase_history)

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.PLANNING
    assert after.updated_at == before_updated_at
    assert len(after.phase_history) == before_hist_len


def test_planning_transitions_to_planned_when_response_exists_without_processing(
    sessions_root: Path, monkeypatch: pytest.MonkeyPatch, utf8: str
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
    orch.step(session_id)  # INITIALIZED -> PLANNING

    session_dir = sessions_root / session_id
    (session_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / PROMPTS_DIR / "planning-prompt.md").write_text("PROMPT", encoding=utf8)

    (session_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / RESPONSES_DIR / "planning-response.md").write_text("RESPONSE", encoding=utf8)

    # Guard: no processing in PLANNING; no profile calls
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.PLANNED
    assert after.status == WorkflowStatus.IN_PROGRESS

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def test_planning_prompt_generated_on_entry_from_initialized(
    sessions_root: Path, mock_jpa_mt_profile
) -> None:
    """Prompt generation now happens on entry to PLANNING (in _step_initialized)."""
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

    orch.step(session_id)  # INITIALIZED -> PLANNING (generates prompt)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.PLANNING
    assert after.status == WorkflowStatus.IN_PROGRESS

    session_dir = sessions_root / session_id
    prompt_file = session_dir / "iteration-1" / "planning-prompt.md"
    assert prompt_file.is_file()
    assert mock_jpa_mt_profile.generate_planning_prompt.called


def test_planning_is_noop_when_response_missing(
    sessions_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PLANNING phase is a no-op waiting for response (prompt already exists)."""
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
    orch.step(session_id)  # INITIALIZED -> PLANNING (generates prompt)

    # Guard: profile must not be called in PLANNING phase (only checks for response)
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_updated_at = before.updated_at
    before_hist_len = len(before.phase_history)

    orch.step(session_id)  # PLANNING - no response, stays in PLANNING

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
    orch.step(session_id)  # INITIALIZED -> PLANNING (generates prompt)

    session_dir = sessions_root / session_id
    iteration_dir = session_dir / "iteration-1"
    # Prompt already exists from step above
    (iteration_dir / "planning-response.md").write_text("RESPONSE", encoding=utf8)

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

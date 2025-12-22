"""Tests for WorkflowOrchestrator._prompt_context method."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import (
    Artifact,
    ExecutionMode,
    WorkflowPhase,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _CaptureContextProfile:
    """Stub profile that captures the context passed to prompt generation."""

    def __init__(self) -> None:
        self.captured_context: dict[str, Any] | None = None

    def generate_review_prompt(self, context: dict[str, Any]) -> str:
        self.captured_context = context
        return "REVIEW PROMPT"

    def generate_revision_prompt(self, context: dict[str, Any]) -> str:
        self.captured_context = context
        return "REVISION PROMPT"


def _setup_session_at_phase(
    sessions_root: Path,
    phase: WorkflowPhase,
    iteration: int,
    artifacts: list[Artifact],
) -> tuple[WorkflowOrchestrator, SessionStore, str]:
    """Setup a session at a specific phase with given artifacts."""
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
    it_dir = session_dir / f"iteration-{iteration}"
    it_dir.mkdir(parents=True, exist_ok=True)

    state = store.load(session_id)
    state.current_iteration = iteration
    state.phase = phase
    state.artifacts = artifacts
    store.save(state)

    return orch, store, session_id


def test_prompt_context_includes_code_files_for_reviewing_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REVIEWING phase should include code_files from current iteration."""
    artifacts = [
        Artifact(path="iteration-1/code/Client.java", phase=WorkflowPhase.GENERATED, iteration=1),
        Artifact(path="iteration-1/code/ClientRepository.java", phase=WorkflowPhase.GENERATED, iteration=1),
        Artifact(path="iteration-1/generation-response.md", phase=WorkflowPhase.GENERATING, iteration=1),
    ]

    orch, store, session_id = _setup_session_at_phase(
        sessions_root, WorkflowPhase.REVIEWING, iteration=1, artifacts=artifacts
    )

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    assert stub.captured_context is not None
    assert "code_files" in stub.captured_context
    code_files = stub.captured_context["code_files"]
    assert len(code_files) == 2
    assert "iteration-1/code/Client.java" in code_files
    assert "iteration-1/code/ClientRepository.java" in code_files


def test_prompt_context_includes_code_files_for_revising_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REVISING phase should include code_files from previous iteration (current - 1)."""
    # Iteration 2 means we're revising iteration-1's code
    artifacts = [
        Artifact(path="iteration-1/code/Client.java", phase=WorkflowPhase.GENERATED, iteration=1),
        Artifact(path="iteration-1/code/ClientRepository.java", phase=WorkflowPhase.GENERATED, iteration=1),
        Artifact(path="iteration-1/review-response.md", phase=WorkflowPhase.REVIEWED, iteration=1),
    ]

    orch, store, session_id = _setup_session_at_phase(
        sessions_root, WorkflowPhase.REVISING, iteration=2, artifacts=artifacts
    )

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    assert stub.captured_context is not None
    assert "code_files" in stub.captured_context
    code_files = stub.captured_context["code_files"]
    assert len(code_files) == 2
    assert "iteration-1/code/Client.java" in code_files
    assert "iteration-1/code/ClientRepository.java" in code_files


def test_prompt_context_excludes_non_code_artifacts(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """code_files should only include artifacts under iteration-N/code/."""
    artifacts = [
        Artifact(path="iteration-1/code/Client.java", phase=WorkflowPhase.GENERATED, iteration=1),
        Artifact(path="iteration-1/generation-response.md", phase=WorkflowPhase.GENERATING, iteration=1),
        Artifact(path="iteration-1/review-prompt.md", phase=WorkflowPhase.REVIEWING, iteration=1),
    ]

    orch, store, session_id = _setup_session_at_phase(
        sessions_root, WorkflowPhase.REVIEWING, iteration=1, artifacts=artifacts
    )

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    assert stub.captured_context is not None
    code_files = stub.captured_context["code_files"]
    assert len(code_files) == 1
    assert "iteration-1/code/Client.java" in code_files


def test_prompt_context_empty_code_files_when_no_artifacts(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """code_files should be empty list when no code artifacts exist."""
    orch, store, session_id = _setup_session_at_phase(
        sessions_root, WorkflowPhase.REVIEWING, iteration=1, artifacts=[]
    )

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    assert stub.captured_context is not None
    assert "code_files" in stub.captured_context
    assert stub.captured_context["code_files"] == []

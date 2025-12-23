"""Tests for WorkflowOrchestrator._prompt_context method.

Prompt generation now happens on entry to ING phases, so these tests
set up the previous phase and then trigger the transition to capture
the context passed to prompt generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
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

    def process_review_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.FAILED)


def test_prompt_context_includes_code_files_for_reviewing_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When entering REVIEWING from GENERATED, code_files from current iteration are included."""
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

    # Set up state in GENERATED with hashed artifacts (approved)
    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED
    state.artifacts = [
        Artifact(path="iteration-1/code/Client.java", phase=WorkflowPhase.GENERATED, iteration=1, sha256="abc123"),
        Artifact(path="iteration-1/code/ClientRepository.java", phase=WorkflowPhase.GENERATED, iteration=1, sha256="def456"),
    ]
    store.save(state)

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    # Step from GENERATED -> REVIEWING (generates review prompt)
    orch.step(session_id)

    assert store.load(session_id).phase == WorkflowPhase.REVIEWING
    assert stub.captured_context is not None
    assert "code_files" in stub.captured_context
    code_files = stub.captured_context["code_files"]
    assert len(code_files) == 2
    assert "iteration-1/code/Client.java" in code_files
    assert "iteration-1/code/ClientRepository.java" in code_files


def test_prompt_context_includes_code_files_for_revising_phase(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When entering REVISING from REVIEWED, code_files from previous iteration are included."""
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
    (it_dir / "review-response.md").write_text("VERDICT: FAIL\n", encoding=utf8)

    # Set up state in REVIEWED with approval and artifacts
    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.REVIEWED
    state.review_approved = True  # Required to process REVIEWED
    state.artifacts = [
        Artifact(path="iteration-1/code/Client.java", phase=WorkflowPhase.GENERATED, iteration=1, sha256="abc123"),
        Artifact(path="iteration-1/code/ClientRepository.java", phase=WorkflowPhase.GENERATED, iteration=1, sha256="def456"),
    ]
    store.save(state)

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    # Step from REVIEWED -> REVISING (generates revision prompt)
    orch.step(session_id)

    assert store.load(session_id).phase == WorkflowPhase.REVISING
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

    # Set up state in GENERATED with mixed artifacts (code and non-code)
    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED
    state.artifacts = [
        Artifact(path="iteration-1/code/Client.java", phase=WorkflowPhase.GENERATED, iteration=1, sha256="abc123"),
        Artifact(path="iteration-1/generation-response.md", phase=WorkflowPhase.GENERATING, iteration=1, sha256="xxx"),
        Artifact(path="iteration-1/review-prompt.md", phase=WorkflowPhase.REVIEWING, iteration=1, sha256="yyy"),
    ]
    store.save(state)

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    # Step from GENERATED -> REVIEWING
    orch.step(session_id)

    assert stub.captured_context is not None
    code_files = stub.captured_context["code_files"]
    assert len(code_files) == 1
    assert "iteration-1/code/Client.java" in code_files


def test_prompt_context_empty_code_files_when_no_code_artifacts(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """code_files should be empty list when no code artifacts exist (only iteration-N/code/)."""
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

    # Set up state in GENERATED with a code artifact (required to pass gate)
    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED
    # Need at least one code artifact to pass the GENERATED gate
    state.artifacts = [
        Artifact(path="iteration-1/code/dummy.txt", phase=WorkflowPhase.GENERATED, iteration=1, sha256="abc123"),
    ]
    store.save(state)

    stub = _CaptureContextProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    assert stub.captured_context is not None
    assert "code_files" in stub.captured_context
    # One code file exists
    assert stub.captured_context["code_files"] == ["iteration-1/code/dummy.txt"]

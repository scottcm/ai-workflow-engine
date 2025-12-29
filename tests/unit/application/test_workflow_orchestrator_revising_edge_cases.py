"""Tests for edge cases in REVISING and REVIEWED phases.

Covers:
- CANCELLED status in _step_revising transitions to CANCELLED phase
- ImportError fallback in _step_revising transitions to ERROR phase
- Unknown ProcessingResult status in _step_reviewed returns without transition
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import sys

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


class _StubRevisionProcessProfile:
    """Stub profile that returns configurable ProcessingResult for revision."""

    def __init__(
        self,
        status: WorkflowStatus = WorkflowStatus.SUCCESS,
        error_message: str | None = None,
        write_plan=None,
    ) -> None:
        self.process_called = 0
        self._status = status
        self._error_message = error_message
        self._write_plan = write_plan

    def process_revision_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(
            status=self._status,
            error_message=self._error_message,
            write_plan=self._write_plan,
        )


class _StubReviewProcessProfile:
    """Stub profile that returns configurable ProcessingResult for review."""

    def __init__(
        self,
        status: WorkflowStatus = WorkflowStatus.SUCCESS,
        error_message: str | None = None,
    ) -> None:
        self.process_called = 0
        self._status = status
        self._error_message = error_message

    def process_review_response(self, content: str) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(
            status=self._status,
            error_message=self._error_message,
        )


def _arrange_at_revising_with_prompt(
    sessions_root: Path, utf8: str, valid_jpa_mt_context: dict[str, Any]
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    """Arrange state at REVISING with revision prompt already written."""
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-2"
    it_dir.mkdir(parents=True, exist_ok=True)

    # Simulate prompt was already generated on entry to REVISING
    (it_dir / "revision-prompt.md").write_text("REVISION PROMPT", encoding=utf8)

    state = store.load(session_id)
    state.current_iteration = 2
    state.phase = WorkflowPhase.REVISING
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    return orch, store, session_id, it_dir


def _arrange_at_reviewed_with_response(
    sessions_root: Path, utf8: str, valid_jpa_mt_context: dict[str, Any]
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    """Arrange state at REVIEWED with review response and review_approved=True."""
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
    it_dir.mkdir(parents=True, exist_ok=True)

    # Write review response
    (it_dir / "review-response.md").write_text(
        "@@@REVIEW_META\nverdict: PASS\nissues_total: 0\nissues_critical: 0\nmissing_inputs: 0\n@@@\n",
        encoding=utf8,
    )

    state = store.load(session_id)
    state.current_iteration = 1
    state.phase = WorkflowPhase.REVIEWED
    state.status = WorkflowStatus.IN_PROGRESS
    state.review_approved = True  # Must be True to process review
    store.save(state)

    return orch, store, session_id, it_dir


def test_revising_cancelled_status_transitions_to_cancelled(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
    valid_jpa_mt_context: dict[str, Any],
) -> None:
    """When process_revision_response returns CANCELLED, transition to CANCELLED phase."""
    orch, store, session_id, it_dir = _arrange_at_revising_with_prompt(
        sessions_root, utf8, valid_jpa_mt_context
    )

    # Write revision response
    (it_dir / "revision-response.md").write_text(
        "<<<FILE: x.java>>>\nclass X {}\n", encoding=utf8
    )

    # Stub profile to return CANCELLED
    proc = _StubRevisionProcessProfile(status=WorkflowStatus.CANCELLED)
    monkeypatch.setattr(
        ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc)
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.CANCELLED
    assert after.status == WorkflowStatus.CANCELLED
    assert proc.process_called == 1


def test_revising_fallback_bundle_extractor_import_error_transitions_to_error(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
    valid_jpa_mt_context: dict[str, Any],
) -> None:
    """When write_plan is None and bundle_extractor import fails, transition to ERROR."""
    import builtins
    import importlib

    orch, store, session_id, it_dir = _arrange_at_revising_with_prompt(
        sessions_root, utf8, valid_jpa_mt_context
    )

    # Write revision response
    (it_dir / "revision-response.md").write_text(
        "<<<FILE: x.java>>>\nclass X {}\n", encoding=utf8
    )

    # Stub profile to return SUCCESS but with NO write_plan (triggers fallback)
    proc = _StubRevisionProcessProfile(
        status=WorkflowStatus.SUCCESS, write_plan=None
    )
    monkeypatch.setattr(
        ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc)
    )

    # Make the bundle_extractor import fail via importlib.import_module
    # which is what the orchestrator uses
    original_import_module = importlib.import_module

    def mock_import_module(name, package=None):
        if "bundle_extractor" in name:
            raise ImportError(f"Mocked import error for {name}")
        return original_import_module(name, package)

    # Remove cached module if exists
    modules_to_remove = [k for k in list(sys.modules.keys()) if "bundle_extractor" in k]
    removed_modules = {}
    for mod in modules_to_remove:
        removed_modules[mod] = sys.modules.pop(mod)

    monkeypatch.setattr(importlib, "import_module", mock_import_module)

    try:
        orch.step(session_id)
    finally:
        # Restore modules
        sys.modules.update(removed_modules)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.ERROR
    assert after.status == WorkflowStatus.ERROR
    assert proc.process_called == 1


def test_reviewed_unknown_result_status_noop(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
    valid_jpa_mt_context: dict[str, Any],
) -> None:
    """When process_review_response returns an unexpected status, no transition occurs."""
    orch, store, session_id, it_dir = _arrange_at_reviewed_with_response(
        sessions_root, utf8, valid_jpa_mt_context
    )

    before = store.load(session_id)
    before_phase = before.phase
    before_hist_len = len(before.phase_history)

    # Create a mock status that isn't SUCCESS, FAILED, ERROR, or CANCELLED
    # by returning IN_PROGRESS (not a valid review outcome)
    proc = _StubReviewProcessProfile(status=WorkflowStatus.IN_PROGRESS)
    monkeypatch.setattr(
        ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc)
    )

    orch.step(session_id)

    after = store.load(session_id)
    # Should remain in REVIEWED - no transition
    assert after.phase == before_phase
    assert len(after.phase_history) == before_hist_len
    assert proc.process_called == 1
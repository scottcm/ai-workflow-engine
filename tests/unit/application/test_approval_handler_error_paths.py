"""Tests for error paths in ApprovalHandler.

Covers:
- Provider role not configured raises ValueError
- extract_files function missing from profile module raises ValueError
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
import sys

import pytest

from aiwf.application.approval_handler import IngPhaseApprovalHandler, _extract_and_write_code_files
from aiwf.application.approval_specs import ING_APPROVAL_SPECS
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)


def _build_state(
    session_id: str,
    phase: WorkflowPhase,
    current_iteration: int,
    providers: dict[str, str],
    profile: str = "jpa-mt",
) -> WorkflowState:
    """Build a minimal WorkflowState for testing."""
    return WorkflowState(
        session_id=session_id,
        profile=profile,
        scope="test-scope",
        entity="TestEntity",
        providers=providers,
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=phase,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=current_iteration,
        standards_hash="test-hash",
        phase_history=[PhaseTransition(phase=phase, status=WorkflowStatus.IN_PROGRESS)],
    )


def test_approve_ing_provider_role_missing_raises_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approving an ING phase without configured provider role raises ValueError."""
    session_dir = tmp_path / "test-session"
    session_dir.mkdir(parents=True, exist_ok=True)

    phase = WorkflowPhase.GENERATING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]

    # Create prompt file so we get past the file check
    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    prompt_path = session_dir / prompt_relpath
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("test prompt\n", encoding="utf-8")

    # Create state with EMPTY providers dict (missing the required role)
    state = _build_state(
        session_id="test-session",
        phase=phase,
        current_iteration=iteration,
        providers={},  # Missing 'generator' role
    )

    handler = IngPhaseApprovalHandler()

    with pytest.raises(ValueError) as exc_info:
        handler.handle(session_dir=session_dir, state=state, hash_prompts=False)

    # Verify error message mentions the missing role
    assert "generator" in str(exc_info.value).lower()
    assert "not configured" in str(exc_info.value).lower() or "provider" in str(exc_info.value).lower()


def test_approve_ing_provider_role_wrong_role_raises_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approving an ING phase with wrong provider role key raises ValueError."""
    session_dir = tmp_path / "test-session"
    session_dir.mkdir(parents=True, exist_ok=True)

    phase = WorkflowPhase.REVIEWING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]

    # Create prompt file
    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    prompt_path = session_dir / prompt_relpath
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("test prompt\n", encoding="utf-8")

    # Create state with wrong provider role (has 'generator' but needs 'reviewer')
    state = _build_state(
        session_id="test-session",
        phase=phase,
        current_iteration=iteration,
        providers={"generator": "fake-llm"},  # Missing 'reviewer' role
    )

    handler = IngPhaseApprovalHandler()

    with pytest.raises(ValueError) as exc_info:
        handler.handle(session_dir=session_dir, state=state, hash_prompts=False)

    assert "reviewer" in str(exc_info.value).lower()


def test_extract_code_files_missing_function_raises_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile module without extract_files function raises ValueError."""
    session_dir = tmp_path / "test-session"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create a fake profile module without extract_files
    fake_module = ModuleType("fake_bundle_extractor")
    # Don't add extract_files - that's the point!

    # Use a custom profile name that maps to our fake module
    state = _build_state(
        session_id="test-session",
        phase=WorkflowPhase.GENERATING,
        current_iteration=1,
        providers={"generator": "fake-llm"},
        profile="fake_profile",
    )

    # Monkeypatch importlib.import_module to return our fake module
    def mock_import_module(name):
        if "bundle_extractor" in name:
            return fake_module
        # Let real imports through
        import importlib
        return importlib.__import__(name)

    import importlib
    monkeypatch.setattr(importlib, "import_module", mock_import_module)

    with pytest.raises(ValueError) as exc_info:
        _extract_and_write_code_files(
            session_dir=session_dir,
            state=state,
            response_content="<<<FILE: test.java>>>\nclass Test {}\n",
        )

    error_msg = str(exc_info.value)
    assert "fake_profile" in error_msg
    assert "extract_files" in error_msg


def test_extract_code_files_module_has_function_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile module with extract_files function succeeds."""
    session_dir = tmp_path / "test-session"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create iteration directory
    iteration_dir = session_dir / "iteration-1" / "code"
    iteration_dir.mkdir(parents=True, exist_ok=True)

    # Create a fake profile module WITH extract_files
    fake_module = ModuleType("fake_bundle_extractor")
    fake_module.extract_files = lambda content: {"Test.java": "class Test {}\n"}

    state = _build_state(
        session_id="test-session",
        phase=WorkflowPhase.GENERATING,
        current_iteration=1,
        providers={"generator": "fake-llm"},
        profile="fake_profile",
    )

    import importlib
    original_import = importlib.import_module

    def mock_import_module(name):
        if "bundle_extractor" in name:
            return fake_module
        return original_import(name)

    monkeypatch.setattr(importlib, "import_module", mock_import_module)

    # Should not raise
    _extract_and_write_code_files(
        session_dir=session_dir,
        state=state,
        response_content="<<<FILE: Test.java>>>\nclass Test {}\n",
    )

    # Verify file was written
    code_file = session_dir / "iteration-1" / "code" / "Test.java"
    assert code_file.exists()
    assert "class Test" in code_file.read_text(encoding="utf-8")

    # Verify artifact was added to state
    assert len(state.artifacts) == 1
    assert state.artifacts[0].path == "iteration-1/code/Test.java"
    assert state.artifacts[0].sha256 is not None

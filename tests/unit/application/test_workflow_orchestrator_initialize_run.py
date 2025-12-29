from __future__ import annotations

from pathlib import Path
from typing import Any

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore


def test_initialize_run_creates_session_and_persists_state_without_iteration_dirs(
    sessions_root: Path,
    valid_jpa_mt_context: dict[str, Any],
) -> None:
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"primary": "gemini"},
        execution_mode=ExecutionMode.INTERACTIVE,
        metadata={"test": True},
    )

    state = store.load(session_id)
    assert state.session_id == session_id
    assert state.phase == WorkflowPhase.INITIALIZED
    assert state.status == WorkflowStatus.IN_PROGRESS

    session_dir = sessions_root / session_id
    assert session_dir.is_dir()
    assert not any(p.name.startswith("iteration-") for p in session_dir.iterdir())


def test_initialize_run_normalizes_windows_backslashes_in_metadata(
    sessions_root: Path,
    valid_jpa_mt_context: dict[str, Any],
) -> None:
    """Verify that Windows backslashes in metadata are normalized to forward slashes."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"primary": "gemini"},
        metadata={"some_path": "docs\\samples\\schema.sql"},
    )

    state = store.load(session_id)
    assert state.metadata["some_path"] == "docs/samples/schema.sql"


class TestInitializeRunWithContext:
    """Tests for initialize_run with context parameter."""

    def test_initialize_run_accepts_context(
        self, sessions_root: Path, tmp_path: Path
    ) -> None:
        """initialize_run accepts context dict and stores in state."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=context,
            providers={"primary": "gemini"},
        )
        state = store.load(session_id)
        assert state.context == context

    def test_initialize_run_validates_context(self, sessions_root: Path) -> None:
        """initialize_run raises ValueError for invalid context."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

        invalid_context = {"scope": "invalid"}  # Missing required fields
        import pytest
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(
                profile="jpa-mt",
                context=invalid_context,
                providers={"primary": "gemini"},
            )
        assert "validation" in str(exc_info.value).lower()

    def test_initialize_run_validation_error_is_actionable(self, sessions_root: Path) -> None:
        """Validation error message includes field name and constraint."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

        invalid_context = {"scope": "wrong", "entity": "Foo"}  # scope invalid, others missing
        import pytest
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(
                profile="jpa-mt",
                context=invalid_context,
                providers={"primary": "gemini"},
            )
        error_msg = str(exc_info.value)
        # Should mention the problematic field
        assert "scope" in error_msg or "table" in error_msg or "bounded_context" in error_msg

"""Tests for orchestrator-level ProviderError handling in approve().

These tests verify that the orchestrator correctly handles ProviderError
raised during approval flow (as opposed to run_provider tests which verify
propagation).

Key behaviors tested:
- state.status set to ERROR
- state.last_error contains error message
- WORKFLOW_FAILED event emitted
- Phase does not advance
- Session state is persisted
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.errors import ProviderError
from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.provider_factory import ProviderFactory


class FailingGenerateProvider(AIProvider):
    """Provider that fails during generate()."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "failing-generate",
            "description": "Provider that fails during generate",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        pass  # Validation succeeds

    def generate(self, prompt: str, *args, **kwargs) -> str | None:
        raise ProviderError("Connection refused to AI endpoint")


@pytest.fixture
def register_failing_provider():
    """Register failing provider and clean up after."""
    original_registry = dict(ProviderFactory._registry)
    ProviderFactory.register("failing-generate", FailingGenerateProvider)
    yield
    ProviderFactory._registry.clear()
    ProviderFactory._registry.update(original_registry)


@pytest.fixture
def orchestrator_with_session(
    sessions_root: Path, register_failing_provider, valid_jpa_mt_context: dict[str, Any]
) -> tuple[WorkflowOrchestrator, str]:
    """Create orchestrator and initialize a session in PLANNING phase."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        context=valid_jpa_mt_context,
        providers={"planner": "failing-generate"},
    )

    # Step to PLANNING phase to generate prompt
    orchestrator.step(session_id)

    return orchestrator, session_id


class TestOrchestratorProviderErrors:
    """Tests for ProviderError handling in orchestrator.approve()."""

    def test_approve_provider_error_sets_error_status(
        self, orchestrator_with_session: tuple[WorkflowOrchestrator, str]
    ):
        """approve() sets state.status to ERROR when provider raises ProviderError."""
        orchestrator, session_id = orchestrator_with_session

        result = orchestrator.approve(session_id)

        assert result.status == WorkflowStatus.ERROR

    def test_approve_provider_error_sets_last_error(
        self, orchestrator_with_session: tuple[WorkflowOrchestrator, str]
    ):
        """approve() sets state.last_error with error message."""
        orchestrator, session_id = orchestrator_with_session

        result = orchestrator.approve(session_id)

        assert result.last_error is not None
        assert "Connection refused" in result.last_error

    def test_approve_provider_error_does_not_advance_phase(
        self, orchestrator_with_session: tuple[WorkflowOrchestrator, str]
    ):
        """approve() does not advance phase when provider fails."""
        orchestrator, session_id = orchestrator_with_session

        # Verify we're in PLANNING before approve
        state_before = orchestrator.session_store.load(session_id)
        assert state_before.phase == WorkflowPhase.PLANNING

        result = orchestrator.approve(session_id)

        # Phase should remain PLANNING
        assert result.phase == WorkflowPhase.PLANNING

    def test_approve_provider_error_persists_state(
        self, orchestrator_with_session: tuple[WorkflowOrchestrator, str]
    ):
        """approve() persists error state to session store."""
        orchestrator, session_id = orchestrator_with_session

        orchestrator.approve(session_id)

        # Load from store to verify persistence
        reloaded = orchestrator.session_store.load(session_id)
        assert reloaded.status == WorkflowStatus.ERROR
        assert reloaded.last_error is not None
        assert "Connection refused" in reloaded.last_error

    def test_approve_provider_error_emits_workflow_failed_event(
        self, orchestrator_with_session: tuple[WorkflowOrchestrator, str]
    ):
        """approve() emits WORKFLOW_FAILED event when provider fails."""
        orchestrator, session_id = orchestrator_with_session

        # Track emitted events
        emitted_events: list[WorkflowEventType] = []
        original_emit = orchestrator._emit

        def tracking_emit(event_type, state, **kwargs):
            emitted_events.append(event_type)
            return original_emit(event_type, state, **kwargs)

        orchestrator._emit = tracking_emit

        orchestrator.approve(session_id)

        assert WorkflowEventType.WORKFLOW_FAILED in emitted_events

    def test_approve_provider_error_can_retry_after_fix(
        self, sessions_root: Path, register_failing_provider, valid_jpa_mt_context: dict[str, Any]
    ):
        """Workflow can continue after provider error is fixed."""
        # This tests the recovery path

        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "failing-generate"},
        )
        orchestrator.step(session_id)

        # First approve fails
        result = orchestrator.approve(session_id)
        assert result.status == WorkflowStatus.ERROR

        # Simulate "fixing" the provider by providing the response file manually
        session_dir = sessions_root / session_id / "iteration-1"
        response_file = session_dir / "planning-response.md"
        response_file.write_text("# Planning Response\n\nTest plan content.", encoding="utf-8")

        # Update providers to use manual (which will find the response file)
        state = store.load(session_id)
        state.providers["planner"] = "manual"
        # Reset status so workflow can continue
        state.status = WorkflowStatus.IN_PROGRESS
        state.last_error = None
        store.save(state)

        # Now step should work (response file exists)
        result = orchestrator.step(session_id)

        # Should advance to PLANNED
        assert result.phase == WorkflowPhase.PLANNED
        assert result.status == WorkflowStatus.IN_PROGRESS


class TestProviderErrorMessages:
    """Tests for error message quality in provider errors."""

    def test_error_message_includes_provider_context(
        self, orchestrator_with_session: tuple[WorkflowOrchestrator, str]
    ):
        """Error message provides useful context about the failure."""
        orchestrator, session_id = orchestrator_with_session

        result = orchestrator.approve(session_id)

        # The error should be the ProviderError message
        assert result.last_error is not None
        # Should contain the actual error from the provider
        assert "Connection refused" in result.last_error
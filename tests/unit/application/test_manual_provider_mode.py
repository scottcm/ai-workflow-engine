"""Tests for manual provider mode edge cases.

These tests cover scenarios not tested in test_run_provider.py:
- Existing response file skips provider call
- Missing response file issues prompt only
- Switching from manual to auto provider mid-workflow
- User providing response after prompt issued

Note: test_run_provider.py:73-116 tests basic None return behavior.
"""

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.provider_factory import ProviderFactory


class AutoProvider(AIProvider):
    """Provider that returns an automated response."""

    call_count: int = 0

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "auto-provider",
            "description": "Auto provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        pass

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        AutoProvider.call_count += 1
        return "# Auto-generated Response\n\nThis is an automated response."


@pytest.fixture
def register_auto_provider():
    """Register auto provider and clean up after."""
    original_registry = dict(ProviderFactory._registry)
    ProviderFactory.register("auto-provider", AutoProvider)
    AutoProvider.call_count = 0
    yield
    ProviderFactory._registry.clear()
    ProviderFactory._registry.update(original_registry)


class TestManualProviderEdgeCases:
    """Tests for manual provider mode edge cases."""

    def test_manual_provider_does_not_write_response_file(
        self, sessions_root: Path, valid_jpa_mt_context: dict[str, Any]
    ):
        """Manual provider returns None and no response file is written."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(
            session_store=store, sessions_root=sessions_root
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual"},
        )

        # Step to create prompt file
        orchestrator.step(session_id)

        # Approve should not write response (manual provider returns None)
        orchestrator.approve(session_id)

        # Check that response file was NOT written
        response_file = (
            sessions_root / session_id / "iteration-1" / "planning-response.md"
        )
        assert not response_file.exists()

    def test_user_provides_response_after_manual_prompt(
        self, sessions_root: Path, valid_jpa_mt_context: dict[str, Any]
    ):
        """User can provide response file after manual provider prompt issued."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(
            session_store=store, sessions_root=sessions_root
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual"},
        )

        # Step to create prompt file
        orchestrator.step(session_id)

        # First approve does nothing (no response file)
        orchestrator.approve(session_id)

        # Verify we're still in PLANNING (waiting for response)
        state = store.load(session_id)
        assert state.phase == WorkflowPhase.PLANNING

        # User provides response file manually
        response_file = (
            sessions_root / session_id / "iteration-1" / "planning-response.md"
        )
        response_file.write_text(
            "# Planning Response\n\nUser-provided plan content.",
            encoding="utf-8",
        )

        # Now step should detect response and advance
        result = orchestrator.step(session_id)

        assert result.phase == WorkflowPhase.PLANNED

    def test_switch_manual_to_auto_provider_mid_workflow(
        self, sessions_root: Path, register_auto_provider, valid_jpa_mt_context: dict[str, Any]
    ):
        """Switching from manual to auto provider continues workflow."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(
            session_store=store, sessions_root=sessions_root
        )

        # Start with manual provider for planning
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={
                "planner": "manual",
                "generator": "auto-provider",
            },
        )

        # Step to PLANNING
        orchestrator.step(session_id)

        # User provides planning response manually
        response_file = (
            sessions_root / session_id / "iteration-1" / "planning-response.md"
        )
        response_file.write_text(
            "# Planning Response\n\nManual plan.",
            encoding="utf-8",
        )

        # Step to PLANNED (processes manual response)
        result = orchestrator.step(session_id)
        assert result.phase == WorkflowPhase.PLANNED

        # Approve to advance
        orchestrator.approve(session_id)

        # Step to GENERATING
        result = orchestrator.step(session_id)
        assert result.phase == WorkflowPhase.GENERATING

        # Reset call count before approve
        AutoProvider.call_count = 0

        # Approve with auto-provider should invoke provider
        orchestrator.approve(session_id)

        # Auto provider should have been called
        assert AutoProvider.call_count == 1

        # Response file should exist (written by auto provider)
        gen_response = (
            sessions_root / session_id / "iteration-1" / "generation-response.md"
        )
        assert gen_response.exists()

    def test_existing_response_allows_step_to_advance(
        self, sessions_root: Path, valid_jpa_mt_context: dict[str, Any]
    ):
        """When response file exists, step can process and advance."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(
            session_store=store, sessions_root=sessions_root
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual"},
        )

        # Step to create prompt
        orchestrator.step(session_id)

        # Pre-create response file (simulating user providing response)
        response_file = (
            sessions_root / session_id / "iteration-1" / "planning-response.md"
        )
        response_file.write_text(
            "# Planning Response\n\nPre-existing response.",
            encoding="utf-8",
        )

        # Step should detect response and advance to PLANNED
        result = orchestrator.step(session_id)

        assert result.phase == WorkflowPhase.PLANNED


class TestManualModeStateTransitions:
    """Tests for state transitions in manual mode."""

    def test_planning_phase_with_manual_provider(
        self, sessions_root: Path, valid_jpa_mt_context: dict[str, Any]
    ):
        """Manual mode correctly handles PLANNING phase."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(
            session_store=store, sessions_root=sessions_root
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual"},
        )

        # Initial state
        state = store.load(session_id)
        assert state.phase == WorkflowPhase.INITIALIZED

        # Step creates prompt
        result = orchestrator.step(session_id)
        assert result.phase == WorkflowPhase.PLANNING

        # Prompt file should exist
        prompt_file = (
            sessions_root / session_id / "iteration-1" / "planning-prompt.md"
        )
        assert prompt_file.exists()

        # Response file should not exist yet
        response_file = (
            sessions_root / session_id / "iteration-1" / "planning-response.md"
        )
        assert not response_file.exists()

    def test_manual_mode_workflow_status_remains_in_progress(
        self, sessions_root: Path, valid_jpa_mt_context: dict[str, Any]
    ):
        """Manual mode keeps status IN_PROGRESS while waiting for response."""
        store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(
            session_store=store, sessions_root=sessions_root
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual"},
        )

        orchestrator.step(session_id)
        orchestrator.approve(session_id)

        state = store.load(session_id)
        # Status should still be IN_PROGRESS, not ERROR or WAITING
        assert state.status == WorkflowStatus.IN_PROGRESS
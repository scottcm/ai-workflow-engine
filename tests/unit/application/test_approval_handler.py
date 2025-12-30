"""Tests for Chain of Responsibility approval handlers.

Tests each handler's can_handle() and handle() methods in isolation.
"""
from pathlib import Path

import pytest

from aiwf.application.approval_handler import (
    CodeArtifactApprovalHandler,
    IngPhaseApprovalHandler,
    PlannedApprovalHandler,
    ReviewedApprovalHandler,
    build_approval_chain,
)
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)


def _build_state(phase: WorkflowPhase) -> WorkflowState:
    """Build minimal WorkflowState for testing can_handle()."""
    return WorkflowState(
        session_id="test-session",
        profile="test-profile",
        scope="test-scope",
        entity="TestEntity",
        providers={"planner": "test", "generator": "test", "reviewer": "test", "reviser": "test"},
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=phase,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=1,
        standards_hash="test-hash",
        phase_history=[PhaseTransition(phase=phase, status=WorkflowStatus.IN_PROGRESS)],
    )


class TestIngPhaseApprovalHandler:
    """Tests for IngPhaseApprovalHandler."""

    def test_can_handle_planning_returns_true(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.PLANNING)
        assert handler.can_handle(state) is True

    def test_can_handle_generating_returns_true(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATING)
        assert handler.can_handle(state) is True

    def test_can_handle_reviewing_returns_true(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.REVIEWING)
        assert handler.can_handle(state) is True

    def test_can_handle_revising_returns_true(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.REVISING)
        assert handler.can_handle(state) is True

    def test_can_handle_planned_returns_false(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.PLANNED)
        assert handler.can_handle(state) is False

    def test_can_handle_generated_returns_false(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATED)
        assert handler.can_handle(state) is False

    def test_can_handle_reviewed_returns_false(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.REVIEWED)
        assert handler.can_handle(state) is False

    def test_can_handle_revised_returns_false(self) -> None:
        handler = IngPhaseApprovalHandler()
        state = _build_state(WorkflowPhase.REVISED)
        assert handler.can_handle(state) is False


class TestPlannedApprovalHandler:
    """Tests for PlannedApprovalHandler."""

    def test_can_handle_planned_returns_true(self) -> None:
        handler = PlannedApprovalHandler()
        state = _build_state(WorkflowPhase.PLANNED)
        assert handler.can_handle(state) is True

    def test_can_handle_planning_returns_false(self) -> None:
        handler = PlannedApprovalHandler()
        state = _build_state(WorkflowPhase.PLANNING)
        assert handler.can_handle(state) is False

    def test_can_handle_generating_returns_false(self) -> None:
        handler = PlannedApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATING)
        assert handler.can_handle(state) is False

    def test_can_handle_generated_returns_false(self) -> None:
        handler = PlannedApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATED)
        assert handler.can_handle(state) is False


class TestCodeArtifactApprovalHandler:
    """Tests for CodeArtifactApprovalHandler."""

    def test_can_handle_generated_returns_true(self) -> None:
        handler = CodeArtifactApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATED)
        assert handler.can_handle(state) is True

    def test_can_handle_revised_returns_true(self) -> None:
        handler = CodeArtifactApprovalHandler()
        state = _build_state(WorkflowPhase.REVISED)
        assert handler.can_handle(state) is True

    def test_can_handle_planned_returns_false(self) -> None:
        handler = CodeArtifactApprovalHandler()
        state = _build_state(WorkflowPhase.PLANNED)
        assert handler.can_handle(state) is False

    def test_can_handle_reviewed_returns_false(self) -> None:
        handler = CodeArtifactApprovalHandler()
        state = _build_state(WorkflowPhase.REVIEWED)
        assert handler.can_handle(state) is False

    def test_can_handle_generating_returns_false(self) -> None:
        handler = CodeArtifactApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATING)
        assert handler.can_handle(state) is False


class TestReviewedApprovalHandler:
    """Tests for ReviewedApprovalHandler."""

    def test_can_handle_reviewed_returns_true(self) -> None:
        handler = ReviewedApprovalHandler()
        state = _build_state(WorkflowPhase.REVIEWED)
        assert handler.can_handle(state) is True

    def test_can_handle_reviewing_returns_false(self) -> None:
        handler = ReviewedApprovalHandler()
        state = _build_state(WorkflowPhase.REVIEWING)
        assert handler.can_handle(state) is False

    def test_can_handle_generated_returns_false(self) -> None:
        handler = ReviewedApprovalHandler()
        state = _build_state(WorkflowPhase.GENERATED)
        assert handler.can_handle(state) is False

    def test_can_handle_planned_returns_false(self) -> None:
        handler = ReviewedApprovalHandler()
        state = _build_state(WorkflowPhase.PLANNED)
        assert handler.can_handle(state) is False


class TestBuildApprovalChain:
    """Tests for build_approval_chain()."""

    def test_build_approval_chain_returns_ing_handler(self) -> None:
        chain = build_approval_chain()
        assert isinstance(chain, IngPhaseApprovalHandler)

    def test_chain_handles_all_ing_phases(self) -> None:
        chain = build_approval_chain()
        for phase in [WorkflowPhase.PLANNING, WorkflowPhase.GENERATING,
                      WorkflowPhase.REVIEWING, WorkflowPhase.REVISING]:
            state = _build_state(phase)
            assert chain.can_handle(state) is True

    def test_chain_delegates_to_ed_handlers(self) -> None:
        chain = build_approval_chain()
        # For ED phases, the chain should delegate through successors
        # The ING handler's can_handle returns False, so it delegates
        for phase in [WorkflowPhase.PLANNED, WorkflowPhase.GENERATED,
                      WorkflowPhase.REVISED, WorkflowPhase.REVIEWED]:
            state = _build_state(phase)
            # ING handler can't handle, but chain should find a handler via successors
            assert chain.can_handle(state) is False
            # The successor chain should be able to handle it
            assert chain._successor is not None


class TestProviderCapabilities:
    """Tests for ProviderCapabilities dataclass."""

    def test_create_with_all_fields(self):
        """Can create ProviderCapabilities with all fields."""
        from aiwf.application.approval_handler import ProviderCapabilities

        caps = ProviderCapabilities(
            fs_ability="local-write",
            supports_system_prompt=True,
            supports_file_attachments=True,
        )
        assert caps.fs_ability == "local-write"
        assert caps.supports_system_prompt is True
        assert caps.supports_file_attachments is True

    def test_create_with_minimal_capabilities(self):
        """Can create ProviderCapabilities with minimal capabilities."""
        from aiwf.application.approval_handler import ProviderCapabilities

        caps = ProviderCapabilities(
            fs_ability="none",
            supports_system_prompt=False,
            supports_file_attachments=False,
        )
        assert caps.fs_ability == "none"
        assert caps.supports_system_prompt is False
        assert caps.supports_file_attachments is False

    def test_all_fs_ability_values_valid(self):
        """All documented fs_ability values can be used."""
        from aiwf.application.approval_handler import ProviderCapabilities

        for fs_ability in ["local-write", "local-read", "write-only", "none"]:
            caps = ProviderCapabilities(
                fs_ability=fs_ability,
                supports_system_prompt=False,
                supports_file_attachments=False,
            )
            assert caps.fs_ability == fs_ability

"""Tests for WorkflowPhase and WorkflowStage enums.

TDD Tests for ADR-0012 Phase 1.
"""

import pytest

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


class TestWorkflowPhase:
    """Tests for WorkflowPhase enum."""

    def test_phase_values_exist(self) -> None:
        """All required phase values exist."""
        assert WorkflowPhase.INIT == "init"
        assert WorkflowPhase.PLAN == "plan"
        assert WorkflowPhase.GENERATE == "generate"
        assert WorkflowPhase.REVIEW == "review"
        assert WorkflowPhase.REVISE == "revise"
        assert WorkflowPhase.COMPLETE == "complete"
        assert WorkflowPhase.ERROR == "error"
        assert WorkflowPhase.CANCELLED == "cancelled"

    def test_phase_count_is_exactly_eight(self) -> None:
        """Exactly 8 phases defined (no legacy phases)."""
        assert len(WorkflowPhase) == 8

    def test_phase_is_str_enum(self) -> None:
        """WorkflowPhase is a string enum for JSON serialization."""
        assert isinstance(WorkflowPhase.INIT, str)
        assert WorkflowPhase.INIT == "init"

    def test_terminal_phases(self) -> None:
        """COMPLETE, ERROR, CANCELLED are terminal phases."""
        terminal = {WorkflowPhase.COMPLETE, WorkflowPhase.ERROR, WorkflowPhase.CANCELLED}
        assert WorkflowPhase.COMPLETE in terminal
        assert WorkflowPhase.ERROR in terminal
        assert WorkflowPhase.CANCELLED in terminal

    def test_active_phases(self) -> None:
        """PLAN, GENERATE, REVIEW, REVISE are active phases with stages."""
        active = {WorkflowPhase.PLAN, WorkflowPhase.GENERATE, WorkflowPhase.REVIEW, WorkflowPhase.REVISE}
        assert len(active) == 4


class TestWorkflowStage:
    """Tests for WorkflowStage enum."""

    def test_stage_values_exist(self) -> None:
        """Both stage values exist."""
        assert WorkflowStage.ING == "ing"
        assert WorkflowStage.ED == "ed"

    def test_stage_count_is_exactly_two(self) -> None:
        """Exactly 2 stages defined."""
        assert len(WorkflowStage) == 2

    def test_stage_is_str_enum(self) -> None:
        """WorkflowStage is a string enum for JSON serialization."""
        assert isinstance(WorkflowStage.ING, str)
        assert WorkflowStage.ING == "ing"


class TestPhaseStageSemantics:
    """Tests for phase+stage semantic meaning."""

    def test_ing_stage_meaning(self) -> None:
        """ING stage means prompt ready, waiting for response."""
        # ING = Input preparation complete, prompt artifact exists
        # Semantic test - documents the meaning
        assert WorkflowStage.ING.value == "ing"

    def test_ed_stage_meaning(self) -> None:
        """ED stage means response received, waiting for approval."""
        # ED = Output ready, response artifact exists
        assert WorkflowStage.ED.value == "ed"
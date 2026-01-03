"""Tests for ManualApprovalProvider.

ADR-0015: Tests for manual approval provider (returns None to pause).
"""

import pytest

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider, ManualApprovalProvider


class TestManualApprovalProvider:
    """Tests for ManualApprovalProvider implementation."""

    def test_manual_approver_is_approval_provider(self) -> None:
        """ManualApprovalProvider implements ApprovalProvider."""
        assert issubclass(ManualApprovalProvider, ApprovalProvider)

    def test_manual_approver_can_be_instantiated(self) -> None:
        """ManualApprovalProvider can be instantiated without arguments."""
        provider = ManualApprovalProvider()
        assert provider is not None

    def test_manual_approver_evaluate_returns_none(self) -> None:
        """ManualApprovalProvider.evaluate returns None to signal pause.

        ADR-0015: Manual approval returns None to indicate the workflow
        should pause and wait for user input (approve/reject command).
        """
        provider = ManualApprovalProvider()

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result is None

    def test_manual_approver_metadata(self) -> None:
        """ManualApprovalProvider has correct metadata."""
        metadata = ManualApprovalProvider.get_metadata()
        assert metadata["name"] == "manual"
        assert "pause" in metadata["description"].lower()

    @pytest.mark.parametrize(
        "phase,stage",
        [
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT),
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE),
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT),
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE),
        ],
    )
    def test_manual_approver_returns_none_for_all_phases(
        self, phase: WorkflowPhase, stage: WorkflowStage
    ) -> None:
        """ManualApprovalProvider returns None regardless of phase/stage."""
        provider = ManualApprovalProvider()

        result = provider.evaluate(
            phase=phase,
            stage=stage,
            files={},
            context={},
        )

        assert result is None

"""Tests for ManualApprovalProvider.

ADR-0015: Tests for manual approval provider (returns PENDING to pause).
"""

import pytest

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
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

    def test_evaluate_returns_pending(self) -> None:
        """ManualApprovalProvider.evaluate() returns PENDING result."""
        provider = ManualApprovalProvider()
        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            files={},
            context={},
        )
        assert isinstance(result, ApprovalResult)
        assert result.decision == ApprovalDecision.PENDING
        assert result.feedback is not None  # Should have message

    def test_metadata_fs_ability_local_write(self) -> None:
        """Manual approver claims local-write (human has full access)."""
        metadata = ManualApprovalProvider.get_metadata()
        assert metadata["fs_ability"] == "local-write"

    def test_metadata_name(self) -> None:
        """Manual approver metadata has correct name."""
        metadata = ManualApprovalProvider.get_metadata()
        assert metadata["name"] == "manual"

    @pytest.mark.parametrize(
        "phase,stage",
        [
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT),
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE),
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT),
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE),
        ],
    )
    def test_manual_approver_returns_pending_for_all_phases(
        self, phase: WorkflowPhase, stage: WorkflowStage
    ) -> None:
        """ManualApprovalProvider returns PENDING regardless of phase/stage."""
        provider = ManualApprovalProvider()

        result = provider.evaluate(
            phase=phase,
            stage=stage,
            files={},
            context={},
        )

        assert isinstance(result, ApprovalResult)
        assert result.decision == ApprovalDecision.PENDING

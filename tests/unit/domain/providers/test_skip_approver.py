"""Tests for SkipApprovalProvider.

ADR-0015: Tests for auto-approve provider.
"""

import pytest

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider, SkipApprovalProvider


class TestSkipApprovalProvider:
    """Tests for SkipApprovalProvider implementation."""

    def test_skip_approver_is_approval_provider(self) -> None:
        """SkipApprovalProvider implements ApprovalProvider."""
        assert issubclass(SkipApprovalProvider, ApprovalProvider)

    def test_skip_approver_can_be_instantiated(self) -> None:
        """SkipApprovalProvider can be instantiated without arguments."""
        provider = SkipApprovalProvider()
        assert provider is not None

    def test_skip_approver_always_approves(self) -> None:
        """SkipApprovalProvider.evaluate always returns APPROVED."""
        provider = SkipApprovalProvider()

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={"plan.md": "# Plan content"},
            context={"session_id": "test-123"},
        )

        assert isinstance(result, ApprovalResult)
        assert result.decision == ApprovalDecision.APPROVED

    def test_skip_approver_approves_without_feedback(self) -> None:
        """SkipApprovalProvider.evaluate returns approval without feedback."""
        provider = SkipApprovalProvider()

        result = provider.evaluate(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.feedback is None

    def test_skip_approver_metadata(self) -> None:
        """SkipApprovalProvider has correct metadata."""
        metadata = SkipApprovalProvider.get_metadata()
        assert metadata["name"] == "skip"
        assert "auto" in metadata["description"].lower()

    @pytest.mark.parametrize(
        "phase,stage",
        [
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT),
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE),
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT),
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE),
            (WorkflowPhase.REVIEW, WorkflowStage.PROMPT),
            (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE),
            (WorkflowPhase.REVISE, WorkflowStage.PROMPT),
            (WorkflowPhase.REVISE, WorkflowStage.RESPONSE),
        ],
    )
    def test_skip_approver_approves_all_phases_and_stages(
        self, phase: WorkflowPhase, stage: WorkflowStage
    ) -> None:
        """SkipApprovalProvider approves regardless of phase/stage."""
        provider = SkipApprovalProvider()

        result = provider.evaluate(
            phase=phase,
            stage=stage,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED

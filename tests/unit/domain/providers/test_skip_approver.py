"""Tests for SkipApprovalProvider.

TDD Tests for ADR-0012 Phase 3.
"""

import pytest

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.skip_approver import SkipApprovalProvider


class TestSkipApprovalProvider:
    """Tests for SkipApprovalProvider implementation."""

    def test_skip_approver_is_approval_provider(self) -> None:
        """SkipApprovalProvider implements ApprovalProvider."""
        assert issubclass(SkipApprovalProvider, ApprovalProvider)

    def test_skip_approver_can_be_instantiated(self) -> None:
        """SkipApprovalProvider can be instantiated without arguments."""
        provider = SkipApprovalProvider()
        assert provider is not None

    def test_skip_approver_requires_no_user_input(self) -> None:
        """SkipApprovalProvider.requires_user_input is False."""
        provider = SkipApprovalProvider()
        assert provider.requires_user_input is False

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
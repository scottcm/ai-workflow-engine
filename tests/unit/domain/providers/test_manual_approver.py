"""Tests for ManualApprovalProvider.

TDD Tests for ADR-0012 Phase 3.
"""

import pytest

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.manual_approver import ManualApprovalProvider


class TestManualApprovalProvider:
    """Tests for ManualApprovalProvider implementation."""

    def test_manual_approver_is_approval_provider(self) -> None:
        """ManualApprovalProvider implements ApprovalProvider."""
        assert issubclass(ManualApprovalProvider, ApprovalProvider)

    def test_manual_approver_can_be_instantiated(self) -> None:
        """ManualApprovalProvider can be instantiated without arguments."""
        provider = ManualApprovalProvider()
        assert provider is not None

    def test_manual_approver_requires_user_input(self) -> None:
        """ManualApprovalProvider.requires_user_input is True."""
        provider = ManualApprovalProvider()
        assert provider.requires_user_input is True

    def test_manual_approver_evaluate_raises_runtime_error(self) -> None:
        """ManualApprovalProvider.evaluate raises RuntimeError.

        The evaluate method should never be called for manual approval.
        Approval comes from CLI commands (approve/reject), not from evaluate().
        """
        provider = ManualApprovalProvider()

        with pytest.raises(RuntimeError) as exc_info:
            provider.evaluate(
                phase=WorkflowPhase.PLAN,
                stage=WorkflowStage.RESPONSE,
                files={},
                context={},
            )

        assert "should not be called" in str(exc_info.value).lower()
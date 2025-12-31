"""Skip approval provider - always approves.

ADR-0012 Phase 3: Auto-approve for fully automated workflows.
"""

from typing import Any

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider


class SkipApprovalProvider(ApprovalProvider):
    """Approval provider that always approves.

    Used for fully automated workflows where no human review is needed.
    """

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Always returns APPROVED without feedback."""
        return ApprovalResult(decision=ApprovalDecision.APPROVED)

    @property
    def requires_user_input(self) -> bool:
        """Skip provider does not require user input."""
        return False
"""Manual approval provider - requires user CLI command.

ADR-0012 Phase 3: Human-in-the-loop approval for interactive workflows.
"""

from typing import Any

from aiwf.domain.models.approval_result import ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider


class ManualApprovalProvider(ApprovalProvider):
    """Approval provider that requires user CLI command.

    Used for interactive workflows where a human reviews and
    explicitly approves/rejects via CLI commands.

    The evaluate() method should never be called - approval comes
    from the CLI (approve/reject commands), not from this provider.
    """

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Should not be called - raises RuntimeError.

        Manual approval comes from CLI commands, not evaluate().
        """
        raise RuntimeError(
            "ManualApprovalProvider.evaluate() should not be called. "
            "Approval comes from CLI commands (approve/reject)."
        )

    @property
    def requires_user_input(self) -> bool:
        """Manual provider requires user input."""
        return True
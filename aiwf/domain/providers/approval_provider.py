"""Approval providers for workflow gates.

ADR-0015: Generic approvers that receive phase, stage, files, context.
Profiles contribute criteria to context - approvers don't contain domain knowledge.
"""

from abc import ABC, abstractmethod
from typing import Any

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision


class ApprovalProvider(ABC):
    """Abstract base class for approval providers.

    Approval providers evaluate content at workflow gates and return
    APPROVED or REJECTED decisions. They are generic - they receive
    phase, stage, files, and context, and make decisions based on that.

    Built-in providers:
    - SkipApprovalProvider: Auto-approve (no gate)
    - ManualApprovalProvider: Pause for user decision

    Any ResponseProvider can be used as an approver via AIApprovalProvider adapter.
    """

    @abstractmethod
    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult | None:
        """Evaluate content and return approval decision.

        Args:
            phase: Current workflow phase (plan, generate, review, revise)
            stage: Current stage (prompt or response)
            files: Dict of filepath -> content. None value means provider should
                   read file directly (for local-read/write capable providers).
            context: Session metadata and criteria, including:
                - session_id: Session identifier
                - iteration: Current iteration number
                - allow_rewrite: Whether approver can suggest content rewrites
                - criteria_file: Optional path to approval criteria
                - standards_file: Optional path to coding standards
                - plan_file: Path to plan (for generate/review context)
                - review_file: Path to review (for revise context)

        Returns:
            ApprovalResult with decision, feedback, and optional suggested_content.
            Returns None to signal workflow should pause for user input.
        """
        ...

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery."""
        return {
            "name": "base",
            "description": "Base approval provider",
            "fs_ability": "none",
        }


class SkipApprovalProvider(ApprovalProvider):
    """Auto-approve provider. Always returns APPROVED.

    Use this for stages where no approval is needed and the workflow
    should continue immediately.
    """

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Always approve."""
        return ApprovalResult(decision=ApprovalDecision.APPROVED)

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "skip",
            "description": "Auto-approve (no gate)",
            "fs_ability": "none",
        }


class ManualApprovalProvider(ApprovalProvider):
    """Manual approval provider. Pauses workflow for user decision.

    Returns None to signal that the workflow should pause and wait
    for user input (approve/reject command).
    """

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult | None:
        """Return None to signal pause for user input."""
        return None

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "manual",
            "description": "Pause for user approval",
            "fs_ability": "none",
        }

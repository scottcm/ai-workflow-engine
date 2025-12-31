"""Abstract base class for approval providers.

ADR-0012 Phase 3: Strategy pattern for approval decisions.
"""

from abc import ABC, abstractmethod
from typing import Any

from aiwf.domain.models.approval_result import ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


class ApprovalProvider(ABC):
    """Abstract interface for approval providers (Strategy pattern).

    Approval providers evaluate content at approval gates and return
    a decision (APPROVED or REJECTED with feedback).

    Three built-in implementations:
    - SkipApprovalProvider: Always approves (auto-advance)
    - ManualApprovalProvider: Requires user CLI command (pauses workflow)
    - AIApprovalProvider: Delegates decision to an AI provider
    """

    @abstractmethod
    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Evaluate content and return approval decision.

        Args:
            phase: Current workflow phase
            stage: Current workflow stage
            files: Dict of filename -> content (None if file missing)
            context: Additional context (session_id, metadata, etc.)

        Returns:
            ApprovalResult with decision and optional feedback
        """
        ...

    @property
    @abstractmethod
    def requires_user_input(self) -> bool:
        """Whether this provider requires user interaction.

        Returns:
            True if workflow should pause for user input (manual approval).
            False if provider can evaluate automatically (skip, AI).
        """
        ...
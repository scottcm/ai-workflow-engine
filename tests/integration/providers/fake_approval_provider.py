"""Fake approval provider that returns configurable deterministic decisions.

Used for integration testing to simulate approval decisions without AI calls.
"""

from typing import Any

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.approval_provider import ApprovalProvider


class FakeApprovalProvider(ApprovalProvider):
    """Configurable fake approver for integration testing.

    Returns decisions in sequence, cycling through the provided list.
    Tracks all calls for assertions.

    Usage:
        # Always approve
        provider = FakeApprovalProvider()

        # Reject once, then approve
        provider = FakeApprovalProvider(
            decisions=[ApprovalDecision.REJECTED, ApprovalDecision.APPROVED],
            feedback="Needs more detail",
        )

        # Reject with suggested content
        provider = FakeApprovalProvider(
            decisions=[ApprovalDecision.REJECTED],
            feedback="Try this instead",
            suggested_content="# Improved prompt",
        )
    """

    def __init__(
        self,
        decisions: list[ApprovalDecision] | None = None,
        feedback: str | None = None,
        suggested_content: str | None = None,
    ):
        """Initialize the fake approval provider.

        Args:
            decisions: List of decisions to return in sequence.
                       Defaults to [APPROVED].
                       Last decision repeats if calls exceed list length.
            feedback: Feedback to include with REJECTED decisions.
            suggested_content: Suggested content to include with REJECTED decisions.
        """
        self._decisions = decisions or [ApprovalDecision.APPROVED]
        self._feedback = feedback
        self._suggested_content = suggested_content
        self._call_count = 0

        # Track calls for assertions
        self.call_history: list[dict[str, Any]] = []

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "fake-approval",
            "description": "Fake approval provider for testing",
            "fs_ability": "none",
        }

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Return the next decision in sequence.

        Args:
            phase: Current workflow phase
            stage: Current workflow stage
            files: Files being approved
            context: Approval context

        Returns:
            ApprovalResult with next decision in sequence
        """
        # Record the call
        self.call_history.append({
            "phase": phase,
            "stage": stage,
            "files": files,
            "context": context,
        })

        # Get decision (use last if exhausted)
        decision_index = min(self._call_count, len(self._decisions) - 1)
        decision = self._decisions[decision_index]
        self._call_count += 1

        # Build result
        if decision == ApprovalDecision.APPROVED:
            return ApprovalResult(decision=decision)
        else:
            return ApprovalResult(
                decision=decision,
                feedback=self._feedback,
                suggested_content=self._suggested_content,
            )

    def reset(self) -> None:
        """Reset call count and history for reuse."""
        self._call_count = 0
        self.call_history.clear()

    @property
    def call_count(self) -> int:
        """Number of times evaluate() was called."""
        return self._call_count

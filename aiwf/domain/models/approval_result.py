"""Approval decision and result models.

ADR-0012: Binary approval decisions with mandatory feedback on rejection.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class ApprovalDecision(str, Enum):
    """Binary approval decision.

    ADR-0012: Only two outcomes - approved or rejected.
    No "approved with changes" - that's a rejection with feedback.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalResult(BaseModel):
    """Result of an approval evaluation.

    Contains decision and optional feedback.
    Feedback is required for rejections, optional for approvals.

    This model is frozen (immutable) and rejects extra fields to ensure
    approval decisions cannot be modified after creation and unexpected
    provider output is surfaced early.

    Attributes:
        decision: APPROVED or REJECTED
        feedback: Explanation (required for rejections, optional for approvals)
        suggested_content: Optional rewritten content if approver provides a fix.
            When present, the orchestrator may apply this content instead of
            or in addition to the feedback, depending on configuration.
            Whether the orchestrator uses this is controlled by allow_rewrite settings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ApprovalDecision
    feedback: str | None = None
    suggested_content: str | None = None

    @model_validator(mode="after")
    def _validate_rejection_has_feedback(self) -> "ApprovalResult":
        """Ensure rejected decisions include meaningful feedback."""
        if self.decision == ApprovalDecision.REJECTED:
            if self.feedback is None:
                raise ValueError("Rejection requires feedback explaining why")
            if not self.feedback.strip():
                raise ValueError("Rejection feedback cannot be empty or whitespace")
        return self


# Type alias for approval gate outcomes
# None indicates manual approval (pause for user command)
ApprovalOutcome = ApprovalResult | None


def is_manual_pause(outcome: ApprovalOutcome) -> bool:
    """Check if outcome indicates manual approval pause.

    Manual approvers return None to signal the workflow should pause
    and wait for the user's next command (approve/reject/retry).

    Args:
        outcome: Result from ApprovalProvider.evaluate()

    Returns:
        True if the workflow should pause for manual approval
    """
    return outcome is None
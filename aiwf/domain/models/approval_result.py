"""Approval decision and result models.

ADR-0012: Binary approval decisions with mandatory feedback on rejection.
"""

from enum import Enum

from pydantic import BaseModel, model_validator


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
    """

    decision: ApprovalDecision
    feedback: str | None = None

    @model_validator(mode="after")
    def _validate_rejection_has_feedback(self) -> "ApprovalResult":
        """Ensure rejected decisions include meaningful feedback."""
        if self.decision == ApprovalDecision.REJECTED:
            if self.feedback is None:
                raise ValueError("Rejection requires feedback explaining why")
            if not self.feedback.strip():
                raise ValueError("Rejection feedback cannot be empty or whitespace")
        return self
"""Approval decision and result models.

ADR-0012: Three-state approval decisions with mandatory feedback on rejection.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class ApprovalDecision(str, Enum):
    """Approval decision.

    ADR-0012: Three outcomes - approved, rejected, or pending.
    No "approved with changes" - that's a rejection with feedback.
    PENDING means waiting for external input (manual approval).
    """

    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


class ApprovalResult(BaseModel):
    """Result of an approval evaluation.

    Contains decision and optional feedback.
    Feedback is required for rejections, optional for approvals.

    This model is frozen (immutable) and rejects extra fields to ensure
    approval decisions cannot be modified after creation and unexpected
    provider output is surfaced early.

    Attributes:
        decision: APPROVED, REJECTED, or PENDING
        feedback: Explanation (required for rejections, optional for approvals/pending)
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


def validate_approval_result(result: Any) -> ApprovalResult:
    """Validate approval result, catching legacy None returns.

    Migration guard: Some legacy providers may still return None instead
    of ApprovalResult(decision=PENDING). This function catches that and
    provides a clear error message to guide the fix.

    Args:
        result: Result from ApprovalProvider.evaluate()

    Returns:
        The validated ApprovalResult

    Raises:
        TypeError: If result is None (legacy provider not updated)
    """
    if result is None:
        raise TypeError(
            "ApprovalProvider.evaluate() returned None. "
            "This is no longer supported. Return ApprovalResult(decision=PENDING) instead."
        )
    return result
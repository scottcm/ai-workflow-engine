"""Tests for ApprovalDecision and ApprovalResult models.

TDD Tests for ADR-0012 Phase 1.
"""

import pytest
from pydantic import ValidationError

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult


class TestApprovalDecision:
    """Tests for ApprovalDecision enum."""

    def test_decision_values_exist(self) -> None:
        """Both decision values exist."""
        assert ApprovalDecision.APPROVED == "approved"
        assert ApprovalDecision.REJECTED == "rejected"

    def test_decision_count_is_exactly_two(self) -> None:
        """Exactly 2 decisions defined (binary choice)."""
        assert len(ApprovalDecision) == 2

    def test_decision_is_str_enum(self) -> None:
        """ApprovalDecision is a string enum for JSON serialization."""
        assert isinstance(ApprovalDecision.APPROVED, str)


class TestApprovalResult:
    """Tests for ApprovalResult model."""

    def test_approved_without_feedback(self) -> None:
        """Approval can be created without feedback."""
        result = ApprovalResult(decision=ApprovalDecision.APPROVED)
        assert result.decision == ApprovalDecision.APPROVED
        assert result.feedback is None

    def test_approved_with_optional_feedback(self) -> None:
        """Approval can include optional feedback."""
        result = ApprovalResult(
            decision=ApprovalDecision.APPROVED,
            feedback="Looks good, minor suggestion for next iteration",
        )
        assert result.decision == ApprovalDecision.APPROVED
        assert result.feedback == "Looks good, minor suggestion for next iteration"

    def test_rejected_requires_feedback(self) -> None:
        """Rejection must include feedback explaining why."""
        with pytest.raises(ValidationError) as exc_info:
            ApprovalResult(decision=ApprovalDecision.REJECTED)

        # Verify the error mentions feedback
        errors = exc_info.value.errors()
        assert any("feedback" in str(e).lower() for e in errors)

    def test_rejected_with_feedback(self) -> None:
        """Rejection with feedback is valid."""
        result = ApprovalResult(
            decision=ApprovalDecision.REJECTED,
            feedback="Missing required validation logic",
        )
        assert result.decision == ApprovalDecision.REJECTED
        assert result.feedback == "Missing required validation logic"

    def test_rejected_empty_feedback_invalid(self) -> None:
        """Rejection with empty string feedback is invalid."""
        with pytest.raises(ValidationError):
            ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="")

    def test_rejected_whitespace_feedback_invalid(self) -> None:
        """Rejection with whitespace-only feedback is invalid."""
        with pytest.raises(ValidationError):
            ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="   ")


class TestApprovalResultSerialization:
    """Tests for ApprovalResult JSON serialization."""

    def test_model_dump_includes_all_fields(self) -> None:
        """model_dump() includes decision and feedback."""
        result = ApprovalResult(
            decision=ApprovalDecision.APPROVED,
            feedback="Good work",
        )
        data = result.model_dump()
        assert data["decision"] == "approved"
        assert data["feedback"] == "Good work"

    def test_model_dump_excludes_none_feedback(self) -> None:
        """model_dump(exclude_none=True) omits None feedback."""
        result = ApprovalResult(decision=ApprovalDecision.APPROVED)
        data = result.model_dump(exclude_none=True)
        assert "feedback" not in data

    def test_model_validate_from_dict(self) -> None:
        """ApprovalResult can be created from dict."""
        data = {"decision": "approved", "feedback": None}
        result = ApprovalResult.model_validate(data)
        assert result.decision == ApprovalDecision.APPROVED
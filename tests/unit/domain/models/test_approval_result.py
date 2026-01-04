"""Tests for ApprovalDecision and ApprovalResult models.

TDD Tests for ADR-0012 Phase 1.
"""

import pytest
from pydantic import ValidationError

from aiwf.domain.models.approval_result import (
    ApprovalDecision,
    ApprovalResult,
    validate_approval_result,
)


class TestApprovalDecision:
    """Tests for ApprovalDecision enum."""

    def test_decision_values_exist(self) -> None:
        """Both decision values exist."""
        assert ApprovalDecision.APPROVED == "approved"
        assert ApprovalDecision.REJECTED == "rejected"

    def test_decision_is_str_enum(self) -> None:
        """ApprovalDecision is a string enum for JSON serialization."""
        assert isinstance(ApprovalDecision.APPROVED, str)

    def test_pending_decision_exists(self) -> None:
        """PENDING is a valid ApprovalDecision."""
        assert ApprovalDecision.PENDING == "pending"

    def test_approval_decision_has_three_values(self) -> None:
        """ApprovalDecision has exactly three values."""
        assert set(ApprovalDecision) == {
            ApprovalDecision.APPROVED,
            ApprovalDecision.REJECTED,
            ApprovalDecision.PENDING,
        }


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

    def test_pending_result_no_feedback_required(self) -> None:
        """PENDING decisions don't require feedback (unlike REJECTED)."""
        result = ApprovalResult(decision=ApprovalDecision.PENDING)
        assert result.decision == ApprovalDecision.PENDING
        assert result.feedback is None

    def test_pending_result_with_optional_feedback(self) -> None:
        """PENDING can optionally include feedback."""
        result = ApprovalResult(
            decision=ApprovalDecision.PENDING,
            feedback="Awaiting user review"
        )
        assert result.feedback == "Awaiting user review"


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


class TestValidateApprovalResult:
    """Tests for validate_approval_result migration guard."""

    def test_returns_valid_result(self) -> None:
        """validate_approval_result returns a valid ApprovalResult unchanged."""
        result = ApprovalResult(decision=ApprovalDecision.APPROVED)
        validated = validate_approval_result(result)
        assert validated is result

    def test_raises_type_error_for_none(self) -> None:
        """validate_approval_result raises TypeError for None (legacy pattern)."""
        with pytest.raises(TypeError) as exc_info:
            validate_approval_result(None)
        assert "returned None" in str(exc_info.value)
        assert "PENDING" in str(exc_info.value)

    def test_error_message_provides_guidance(self) -> None:
        """Error message guides developer to use PENDING instead."""
        with pytest.raises(TypeError) as exc_info:
            validate_approval_result(None)
        assert "ApprovalResult(decision=PENDING)" in str(exc_info.value)
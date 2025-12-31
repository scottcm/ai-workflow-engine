"""Tests for AIApprovalProvider.

TDD Tests for ADR-0012 Phase 3.
"""

from unittest.mock import Mock

import pytest

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.response_provider import ResponseProvider
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.ai_approver import AIApprovalProvider


class TestAIApprovalProvider:
    """Tests for AIApprovalProvider implementation."""

    def test_ai_approver_is_approval_provider(self) -> None:
        """AIApprovalProvider implements ApprovalProvider."""
        assert issubclass(AIApprovalProvider, ApprovalProvider)

    def test_ai_approver_requires_response_provider(self) -> None:
        """AIApprovalProvider requires a ResponseProvider instance."""
        mock_provider = Mock(spec=ResponseProvider)
        provider = AIApprovalProvider(response_provider=mock_provider)
        assert provider is not None

    def test_ai_approver_requires_no_user_input(self) -> None:
        """AIApprovalProvider.requires_user_input is False."""
        mock_provider = Mock(spec=ResponseProvider)
        provider = AIApprovalProvider(response_provider=mock_provider)
        assert provider.requires_user_input is False


class TestAIApprovalProviderEvaluation:
    """Tests for AIApprovalProvider.evaluate behavior."""

    def test_ai_approver_calls_response_provider_generate(self) -> None:
        """evaluate() calls response provider's generate method."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={"plan.md": "# Plan"},
            context={"session_id": "test"},
        )

        mock_provider.generate.assert_called_once()

    def test_ai_approver_returns_approved_on_approved_response(self) -> None:
        """evaluate() returns APPROVED when AI says APPROVED."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED

    def test_ai_approver_returns_rejected_on_rejected_response(self) -> None:
        """evaluate() returns REJECTED when AI says REJECTED."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "REJECTED: The plan lacks detail"
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert result.feedback is not None

    def test_ai_approver_extracts_feedback_from_rejection(self) -> None:
        """evaluate() extracts feedback from REJECTED response."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "REJECTED: Missing error handling"
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.feedback == "Missing error handling"

    def test_ai_approver_handles_approved_with_comments(self) -> None:
        """evaluate() handles APPROVED with optional comments."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED: Looks good overall"
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED
        # Comments are optional for approvals
        assert result.feedback == "Looks good overall" or result.feedback is None


class TestAIApprovalProviderPromptBuilding:
    """Tests for AIApprovalProvider prompt construction."""

    def test_ai_approver_includes_files_in_prompt(self) -> None:
        """evaluate() includes file contents in prompt."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
            files={"code.py": "def hello(): pass"},
            context={},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        assert "code.py" in prompt or "def hello" in prompt

    def test_ai_approver_includes_phase_context_in_prompt(self) -> None:
        """evaluate() includes phase context in prompt."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={"session_id": "test-session"},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        # Prompt should mention what phase we're approving
        assert "review" in prompt.lower() or "REVIEW" in prompt


class TestAIApprovalProviderEdgeCases:
    """Tests for AIApprovalProvider edge cases."""

    def test_ai_approver_handles_empty_response(self) -> None:
        """evaluate() handles empty response gracefully."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = ""
        provider = AIApprovalProvider(response_provider=mock_provider)

        # Empty response should be treated as rejection (unclear verdict)
        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert result.feedback is not None

    def test_ai_approver_handles_ambiguous_response(self) -> None:
        """evaluate() handles ambiguous response as rejection."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "The code looks okay but has some issues"
        provider = AIApprovalProvider(response_provider=mock_provider)

        # Ambiguous response (no clear APPROVED/REJECTED) should reject
        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert result.feedback is not None

    def test_ai_approver_case_insensitive_approved(self) -> None:
        """evaluate() handles case-insensitive APPROVED."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "approved"
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED

    def test_ai_approver_case_insensitive_rejected(self) -> None:
        """evaluate() handles case-insensitive REJECTED."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "rejected: needs more tests"
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED

    def test_ai_approver_rejected_without_colon_is_ambiguous(self) -> None:
        """REJECTED without colon is treated as ambiguous (fail-safe)."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "REJECTED"  # No colon, no reason
        provider = AIApprovalProvider(response_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        # Should still reject but with generated feedback
        assert result.decision == ApprovalDecision.REJECTED
        assert result.feedback is not None
        assert "without providing reason" in result.feedback.lower() or "unclear" in result.feedback.lower()

    def test_ai_approver_context_does_not_affect_result(self) -> None:
        """Context parameter is accepted but doesn't change approval logic."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        # Call with various context values - result should be the same
        result1 = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )
        result2 = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={"session_id": "test", "extra": "data", "nested": {"key": "value"}},
        )

        assert result1.decision == result2.decision == ApprovalDecision.APPROVED


class TestAIApprovalProviderFileFormatting:
    """Tests for AIApprovalProvider file content formatting."""

    def test_ai_approver_formats_multiline_file_content(self) -> None:
        """Large multiline file content is formatted correctly in prompt."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        multiline_content = """def complex_function():
    '''A function with multiple lines.'''
    result = []
    for i in range(100):
        if i % 2 == 0:
            result.append(i * 2)
        else:
            result.append(i * 3)
    return result
"""

        provider.evaluate(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
            files={"complex.py": multiline_content},
            context={},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")

        # Verify file content is included
        assert "complex.py" in prompt
        assert "complex_function" in prompt
        assert "range(100)" in prompt

    def test_ai_approver_formats_multiple_files(self) -> None:
        """Multiple files are all included in the prompt."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
            files={
                "model.py": "class User: pass",
                "service.py": "class UserService: pass",
                "test_model.py": "def test_user(): pass",
            },
            context={},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")

        # All files should be mentioned
        assert "model.py" in prompt
        assert "service.py" in prompt
        assert "test_model.py" in prompt

    def test_ai_approver_formats_missing_file_marker(self) -> None:
        """None file content shows 'file not found' marker."""
        mock_provider = Mock(spec=ResponseProvider)
        mock_provider.generate.return_value = "APPROVED"
        provider = AIApprovalProvider(response_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
            files={"missing.py": None, "present.py": "content"},
            context={},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")

        assert "missing.py" in prompt
        assert "not found" in prompt.lower()
        assert "present.py" in prompt
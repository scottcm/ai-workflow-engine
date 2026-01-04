"""Tests for AIApprovalProvider.

ADR-0015: Tests for AI-powered approval provider adapter.
"""

from unittest.mock import Mock

import pytest

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.ai_approval_provider import AIApprovalProvider


def _mock_provider_result(response: str) -> AIProviderResult:
    """Create an AIProviderResult with the given response."""
    return AIProviderResult(response=response, files={})


class TestAIApprovalProvider:
    """Tests for AIApprovalProvider implementation."""

    def test_ai_approver_is_approval_provider(self) -> None:
        """AIApprovalProvider implements ApprovalProvider."""
        assert issubclass(AIApprovalProvider, ApprovalProvider)

    def test_ai_approver_requires_ai_provider(self) -> None:
        """AIApprovalProvider requires an AIProvider instance."""
        mock_provider = Mock(spec=AIProvider)
        provider = AIApprovalProvider(ai_provider=mock_provider)
        assert provider is not None

    def test_ai_approver_metadata(self) -> None:
        """AIApprovalProvider has correct metadata."""
        metadata = AIApprovalProvider.get_metadata()
        assert metadata["name"] == "ai-approval"
        assert "varies" in metadata["fs_ability"]


class TestAIApprovalProviderEvaluation:
    """Tests for AIApprovalProvider.evaluate behavior."""

    def test_ai_approver_calls_ai_provider_generate(self) -> None:
        """evaluate() calls AI provider's generate method."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={"plan.md": "# Plan"},
            context={"session_id": "test"},
        )

        mock_provider.generate.assert_called_once()

    def test_ai_approver_returns_approved_on_approved_response(self) -> None:
        """evaluate() returns APPROVED when AI says APPROVED."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED

    def test_ai_approver_returns_rejected_on_rejected_response(self) -> None:
        """evaluate() returns REJECTED when AI says REJECTED."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "DECISION: REJECTED\nFEEDBACK: The plan lacks detail"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

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
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "DECISION: REJECTED\nFEEDBACK: Missing error handling"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.feedback == "Missing error handling"

    def test_ai_approver_handles_approved_with_comments(self) -> None:
        """evaluate() handles APPROVED with optional comments."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "DECISION: APPROVED\nFEEDBACK: Looks good overall"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED


class TestAIApprovalProviderPromptBuilding:
    """Tests for AIApprovalProvider prompt construction."""

    def test_ai_approver_includes_files_in_prompt(self) -> None:
        """evaluate() includes file contents in prompt."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

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
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
            files={"review-response.md": "# Review\nPASS"},
            context={"session_id": "test-session"},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        # Prompt should mention what phase we're approving
        assert "review" in prompt.lower()


class TestAIApprovalProviderEdgeCases:
    """Tests for AIApprovalProvider edge cases."""

    def test_ai_approver_handles_none_response(self) -> None:
        """evaluate() handles None response from provider."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = None
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert result.feedback is not None

    def test_ai_approver_handles_result_with_none_response_text(self) -> None:
        """evaluate() handles AIProviderResult with response=None."""
        mock_provider = Mock(spec=AIProvider)
        # AIProviderResult with files but no response text
        mock_provider.generate.return_value = AIProviderResult(
            response=None, files={"output.txt": "some file content"}
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert "no response text" in result.feedback.lower()

    def test_ai_approver_handles_empty_response(self) -> None:
        """evaluate() handles empty response gracefully."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("")
        provider = AIApprovalProvider(ai_provider=mock_provider)

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
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "The code looks okay but has some issues"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

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
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("decision: approved\nfeedback: none")
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.APPROVED

    def test_ai_approver_case_insensitive_rejected(self) -> None:
        """evaluate() handles case-insensitive REJECTED."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "decision: rejected\nfeedback: needs more tests"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={},
        )

        assert result.decision == ApprovalDecision.REJECTED

    def test_ai_approver_context_does_not_affect_parsing(self) -> None:
        """Context parameter is accepted but doesn't change parsing logic."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

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
            context={"session_id": "test", "extra": "data"},
        )

        assert result1.decision == result2.decision == ApprovalDecision.APPROVED


class TestAIApprovalProviderFileFormatting:
    """Tests for AIApprovalProvider file content formatting."""

    def test_ai_approver_formats_multiline_file_content(self) -> None:
        """Large multiline file content is formatted correctly in prompt."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

        multiline_content = """def complex_function():
    '''A function with multiple lines.'''
    result = []
    for i in range(100):
        result.append(i * 2)
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
        assert "complex.py" in prompt
        assert "complex_function" in prompt

    def test_ai_approver_formats_multiple_files(self) -> None:
        """Multiple files are all included in the prompt."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

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
        assert "model.py" in prompt
        assert "service.py" in prompt
        assert "test_model.py" in prompt

    def test_ai_approver_formats_missing_file_marker(self) -> None:
        """None file content shows appropriate marker."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result("DECISION: APPROVED\nFEEDBACK: None")
        provider = AIApprovalProvider(ai_provider=mock_provider)

        provider.evaluate(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
            files={"missing.py": None, "present.py": "content"},
            context={},
        )

        call_args = mock_provider.generate.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        assert "missing.py" in prompt
        assert "not provided" in prompt.lower() or "not available" in prompt.lower()
        assert "present.py" in prompt


class TestAIApprovalProviderSuggestedContent:
    """Tests for AIApprovalProvider suggested content handling."""

    def test_ai_approver_extracts_suggested_content_when_allowed(self) -> None:
        """Extracts SUGGESTED_CONTENT when allow_rewrite is True."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "DECISION: REJECTED\nFEEDBACK: Fix formatting\nSUGGESTED_CONTENT: # Fixed content"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={"allow_rewrite": True},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert result.suggested_content is not None
        assert "Fixed content" in result.suggested_content

    def test_ai_approver_ignores_suggested_content_when_not_allowed(self) -> None:
        """Ignores SUGGESTED_CONTENT when allow_rewrite is False."""
        mock_provider = Mock(spec=AIProvider)
        mock_provider.generate.return_value = _mock_provider_result(
            "DECISION: REJECTED\nFEEDBACK: Fix formatting\nSUGGESTED_CONTENT: # Fixed content"
        )
        provider = AIApprovalProvider(ai_provider=mock_provider)

        result = provider.evaluate(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            files={},
            context={"allow_rewrite": False},
        )

        assert result.decision == ApprovalDecision.REJECTED
        assert result.suggested_content is None

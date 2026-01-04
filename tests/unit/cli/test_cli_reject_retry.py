"""Tests for reject and retry CLI commands.

TDD Tests for ADR-0012 Phase 6.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from click.testing import CliRunner

from aiwf.interface.cli.cli import cli
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)


def _make_state(
    phase: WorkflowPhase = WorkflowPhase.PLAN,
    stage: WorkflowStage = WorkflowStage.RESPONSE,
    **kwargs,
) -> WorkflowState:
    """Create a minimal WorkflowState for testing."""
    defaults = {
        "session_id": "test-session",
        "profile": "test-profile",
        "context": {},
        "phase": phase,
        "stage": stage,
        "status": WorkflowStatus.IN_PROGRESS,
        "execution_mode": ExecutionMode.INTERACTIVE,
        "ai_providers": {"planner": "manual"},
        "standards_hash": "abc123",
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


class TestRejectCommand:
    """Tests for reject CLI command."""

    def test_reject_requires_session_id(self) -> None:
        """reject command requires session_id argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["reject"])

        assert result.exit_code != 0
        assert "session_id" in result.output.lower() or "missing" in result.output.lower()

    def test_reject_requires_feedback(self) -> None:
        """reject command requires --feedback option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["reject", "test-session"])

        assert result.exit_code != 0
        assert "feedback" in result.output.lower()

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_reject_calls_orchestrator(
        self, mock_orch_cls, mock_store_cls
    ) -> None:
        """reject command calls orchestrator.reject with feedback."""
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        state.approval_feedback = "Bad response"

        mock_orch = Mock()
        mock_orch.reject.return_value = state
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["reject", "test-session", "--feedback", "Bad response"],
        )

        assert result.exit_code == 0
        mock_orch.reject.assert_called_once_with("test-session", feedback="Bad response")

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_reject_json_output(self, mock_orch_cls, mock_store_cls) -> None:
        """reject command outputs JSON when --json flag is set."""
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            approval_feedback="Not detailed enough",
        )

        mock_orch = Mock()
        mock_orch.reject.return_value = state
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--json", "reject", "test-session", "--feedback", "Not detailed enough"],
        )

        assert result.exit_code == 0
        assert '"command":"reject"' in result.output
        assert '"session_id":"test-session"' in result.output
        assert '"feedback":"Not detailed enough"' in result.output

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_reject_plain_text_output(self, mock_orch_cls, mock_store_cls) -> None:
        """reject command outputs plain text using stored feedback."""
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        state.approval_feedback = "Stored feedback"

        mock_orch = Mock()
        mock_orch.reject.return_value = state
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["reject", "test-session", "--feedback", "CLI feedback"],
        )

        assert result.exit_code == 0
        assert "phase=PLAN" in result.output
        assert "rejected=true" in result.output
        # Plain text should use stored feedback, not CLI input
        assert "feedback=Stored feedback" in result.output

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_reject_handles_invalid_command(self, mock_orch_cls, mock_store_cls) -> None:
        """reject command handles InvalidCommand exception."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        mock_orch = Mock()
        mock_orch.reject.side_effect = InvalidCommand(
            "reject", WorkflowPhase.PLAN, WorkflowStage.PROMPT
        )
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["reject", "test-session", "--feedback", "Bad"],
        )

        assert result.exit_code == 1


class TestRetryCommand:
    """Tests for retry CLI command."""

    def test_retry_requires_session_id(self) -> None:
        """retry command requires session_id argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["retry"])

        assert result.exit_code != 0
        assert "session_id" in result.output.lower() or "missing" in result.output.lower()

    def test_retry_requires_feedback(self) -> None:
        """retry command requires --feedback option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["retry", "test-session"])

        assert result.exit_code != 0
        assert "feedback" in result.output.lower()

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_retry_calls_orchestrator(
        self, mock_orch_cls, mock_store_cls
    ) -> None:
        """retry command calls orchestrator.retry with feedback."""
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        state.approval_feedback = "Add more detail"

        mock_orch = Mock()
        mock_orch.retry.return_value = state
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["retry", "test-session", "--feedback", "Add more detail"],
        )

        assert result.exit_code == 0
        mock_orch.retry.assert_called_once_with("test-session", feedback="Add more detail")

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_retry_json_output(self, mock_orch_cls, mock_store_cls) -> None:
        """retry command outputs JSON when --json flag is set."""
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            approval_feedback="Need more examples",
        )

        mock_orch = Mock()
        mock_orch.retry.return_value = state
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--json", "retry", "test-session", "--feedback", "Need more examples"],
        )

        assert result.exit_code == 0
        assert '"command":"retry"' in result.output
        assert '"session_id":"test-session"' in result.output
        assert '"phase":"PLAN"' in result.output

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_retry_plain_text_output(self, mock_orch_cls, mock_store_cls) -> None:
        """retry command outputs plain text by default."""
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)

        mock_orch = Mock()
        mock_orch.retry.return_value = state
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["retry", "test-session", "--feedback", "Retry"],
        )

        assert result.exit_code == 0
        assert "phase=PLAN" in result.output
        assert "stage=PROMPT" in result.output or "prompt" in result.output.lower()

    @patch("aiwf.domain.persistence.session_store.SessionStore")
    @patch("aiwf.application.workflow_orchestrator.WorkflowOrchestrator")
    def test_retry_handles_invalid_command(self, mock_orch_cls, mock_store_cls) -> None:
        """retry command handles InvalidCommand exception."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        mock_orch = Mock()
        mock_orch.retry.side_effect = InvalidCommand(
            "retry", WorkflowPhase.PLAN, WorkflowStage.PROMPT
        )
        mock_orch_cls.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["retry", "test-session", "--feedback", "Retry"],
        )

        assert result.exit_code == 1


class TestOutputModels:
    """Tests for output model structure."""

    def test_reject_output_has_required_fields(self) -> None:
        """RejectOutput has required fields."""
        from aiwf.interface.cli.output_models import RejectOutput

        output = RejectOutput(
            exit_code=0,
            session_id="test",
            phase="PLAN",
            stage="RESPONSE",
            feedback="Bad",
        )

        assert output.command == "reject"
        assert output.session_id == "test"
        assert output.feedback == "Bad"

    def test_retry_output_has_required_fields(self) -> None:
        """RetryOutput has required fields."""
        from aiwf.interface.cli.output_models import RetryOutput

        output = RetryOutput(
            exit_code=0,
            session_id="test",
            phase="PLAN",
            stage="PROMPT",
        )

        assert output.command == "retry"
        assert output.session_id == "test"
        assert output.phase == "PLAN"
        assert output.stage == "PROMPT"
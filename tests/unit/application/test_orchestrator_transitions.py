"""Tests for WorkflowOrchestrator transition logic.

TDD Tests for ADR-0012 Phase 5.
Unit tests for orchestrator methods using mocked providers.
"""

from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pytest

from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator


def _make_state(
    phase: WorkflowPhase = WorkflowPhase.INIT,
    stage: WorkflowStage | None = None,
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
        "providers": {"planner": "manual"},
        "standards_hash": "abc123",
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


class TestOrchestratorInit:
    """Tests for init command."""

    def test_init_from_init_phase_transitions_to_plan_prompt(self) -> None:
        """init from INIT transitions to PLAN[PROMPT]."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.INIT, stage=None)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.init("test-session")

        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.PROMPT

    def test_init_from_non_init_phase_raises_error(self) -> None:
        """init from non-INIT phase raises InvalidCommand."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        from aiwf.application.workflow_orchestrator import InvalidCommand
        with pytest.raises(InvalidCommand):
            orchestrator.init("test-session")


class TestOrchestratorApprove:
    """Tests for approve command."""

    def test_approve_from_plan_prompt_transitions_to_plan_response(self) -> None:
        """approve from PLAN[PROMPT] transitions to PLAN[RESPONSE]."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.approve("test-session")

        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.RESPONSE

    def test_approve_from_plan_response_transitions_to_generate_prompt(
        self, tmp_path: Path
    ) -> None:
        """approve from PLAN[RESPONSE] transitions to GENERATE[PROMPT]."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        # Create the required planning-response.md file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-response.md").write_text("# Plan content")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.approve("test-session")

        assert result.phase == WorkflowPhase.GENERATE
        assert result.stage == WorkflowStage.PROMPT
        assert result.plan_approved is True
        assert result.plan_hash is not None

    def test_approve_from_init_raises_error(self) -> None:
        """approve from INIT raises InvalidCommand."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.INIT, stage=None)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        from aiwf.application.workflow_orchestrator import InvalidCommand
        with pytest.raises(InvalidCommand):
            orchestrator.approve("test-session")


class TestOrchestratorReject:
    """Tests for reject command."""

    def test_reject_from_response_stage_halts_workflow(self) -> None:
        """reject from RESPONSE stage keeps state, sets HALT action."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        result = orchestrator.reject("test-session", feedback="Needs more detail")

        # State stays the same (halted)
        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.RESPONSE
        assert result.approval_feedback == "Needs more detail"

    def test_reject_from_prompt_stage_raises_error(self) -> None:
        """reject from PROMPT stage raises InvalidCommand."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        from aiwf.application.workflow_orchestrator import InvalidCommand
        with pytest.raises(InvalidCommand):
            orchestrator.reject("test-session", feedback="Bad")


class TestOrchestratorRetry:
    """Tests for retry command."""

    def test_retry_from_response_stays_at_response(self) -> None:
        """retry from RESPONSE stays at RESPONSE and regenerates."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.retry("test-session", feedback="Add more detail")

        # Retry stays at RESPONSE stage (regenerates response, not prompt)
        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.RESPONSE

    def test_retry_from_prompt_stage_raises_error(self) -> None:
        """retry from PROMPT stage raises InvalidCommand."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        from aiwf.application.workflow_orchestrator import InvalidCommand
        with pytest.raises(InvalidCommand):
            orchestrator.retry("test-session", feedback="Retry")


class TestOrchestratorCancel:
    """Tests for cancel command."""

    def test_cancel_from_any_active_state_transitions_to_cancelled(self) -> None:
        """cancel from any active state transitions to CANCELLED."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.GENERATE, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        result = orchestrator.cancel("test-session")

        assert result.phase == WorkflowPhase.CANCELLED
        assert result.stage is None
        assert result.status == WorkflowStatus.CANCELLED

    def test_cancel_from_terminal_state_raises_error(self) -> None:
        """cancel from terminal state raises InvalidCommand."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.COMPLETE, stage=None)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        from aiwf.application.workflow_orchestrator import InvalidCommand
        with pytest.raises(InvalidCommand):
            orchestrator.cancel("test-session")


class TestOrchestratorSaveState:
    """Tests for state persistence."""

    def test_commands_save_state_after_transition(self) -> None:
        """Commands save state after successful transition."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with patch.object(orchestrator, "_execute_action"):
            orchestrator.approve("test-session")

        store.save.assert_called_once()


class TestTerminalStateCommands:
    """Tests for commands from terminal states."""

    @pytest.mark.parametrize("terminal_phase", [
        WorkflowPhase.COMPLETE,
        WorkflowPhase.CANCELLED,
        WorkflowPhase.ERROR,
    ])
    def test_all_commands_invalid_from_terminal_states(self, terminal_phase: WorkflowPhase) -> None:
        """All commands raise InvalidCommand from terminal states."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        store = Mock(spec=SessionStore)
        state = _make_state(phase=terminal_phase, stage=None)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with pytest.raises(InvalidCommand):
            orchestrator.init("test-session")

        with pytest.raises(InvalidCommand):
            orchestrator.approve("test-session")

        with pytest.raises(InvalidCommand):
            orchestrator.reject("test-session", feedback="Bad")

        with pytest.raises(InvalidCommand):
            orchestrator.retry("test-session", feedback="Retry")

        with pytest.raises(InvalidCommand):
            orchestrator.cancel("test-session")


class TestFeedbackPersistence:
    """Tests for feedback persistence in reject/retry."""

    def test_retry_stores_feedback_in_approval_feedback(self) -> None:
        """retry stores feedback in approval_feedback field."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.retry("test-session", feedback="Please add details")

        assert result.approval_feedback == "Please add details"


class TestInvalidCommandMessage:
    """Tests for InvalidCommand exception formatting."""

    def test_invalid_command_message_with_stage(self) -> None:
        """InvalidCommand includes phase and stage in message."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        exc = InvalidCommand("approve", WorkflowPhase.PLAN, WorkflowStage.PROMPT)

        assert "approve" in str(exc)
        assert "plan" in str(exc)
        assert "[prompt]" in str(exc)

    def test_invalid_command_message_without_stage(self) -> None:
        """InvalidCommand handles None stage gracefully."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        exc = InvalidCommand("init", WorkflowPhase.COMPLETE, None)

        assert "init" in str(exc)
        assert "complete" in str(exc)
        assert "[" not in str(exc)  # No stage brackets

    def test_invalid_command_stores_attributes(self) -> None:
        """InvalidCommand stores command, phase, and stage as attributes."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        exc = InvalidCommand("approve", WorkflowPhase.PLAN, WorkflowStage.PROMPT)

        assert exc.command == "approve"
        assert exc.phase == WorkflowPhase.PLAN
        assert exc.stage == WorkflowStage.PROMPT


class TestTerminalStatusUpdates:
    """Tests for status updates on terminal transitions."""

    def test_approve_to_complete_sets_success_status(self) -> None:
        """Transitioning to COMPLETE sets status to SUCCESS."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.REVIEW, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        # Mock the action, pre-transition approval, and transition to COMPLETE
        with patch.object(orchestrator, "_execute_action"):
            with patch.object(orchestrator, "_handle_pre_transition_approval"):
                with patch(
                    "aiwf.application.workflow_orchestrator.TransitionTable.get_transition"
                ) as mock_transition:
                    from aiwf.application.transitions import TransitionResult, Action
                    mock_transition.return_value = TransitionResult(
                        phase=WorkflowPhase.COMPLETE,
                        stage=None,
                        action=Action.FINALIZE,
                    )
                    result = orchestrator.approve("test-session")

        assert result.phase == WorkflowPhase.COMPLETE
        assert result.status == WorkflowStatus.SUCCESS
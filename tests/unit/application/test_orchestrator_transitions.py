"""Tests for WorkflowOrchestrator transition logic.

TDD Tests for ADR-0012 Phase 5.
Unit tests for orchestrator methods using mocked providers.
"""

from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pytest

from aiwf.domain.models.workflow_state import (
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.application.approval_config import ApprovalConfig


def _skip_approval_config() -> ApprovalConfig:
    """Create an ApprovalConfig that skips all approval gates."""
    return ApprovalConfig(default_approver="skip")


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
        "ai_providers": {"planner": "manual"},
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
    """Tests for approve command.

    Updated for Phase 2: approve() requires pending_approval=True or last_error.
    """

    def test_approve_from_plan_prompt_transitions_to_plan_response(self) -> None:
        """approve from PLAN[PROMPT] with pending_approval transitions to PLAN[RESPONSE]."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=True,  # Required for Phase 2
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
            approval_config=_skip_approval_config(),
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.approve("test-session")

        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.RESPONSE

    def test_approve_from_plan_response_transitions_to_generate_prompt(
        self, tmp_path: Path
    ) -> None:
        """approve from PLAN[RESPONSE] with pending_approval transitions to GENERATE[PROMPT]."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            pending_approval=True,  # Required for Phase 2
        )
        store.load.return_value = state

        # Create the required planning-response.md file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-response.md").write_text("# Plan content")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=_skip_approval_config(),
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.approve("test-session")

        assert result.phase == WorkflowPhase.GENERATE
        assert result.stage == WorkflowStage.PROMPT
        assert result.plan_approved is True
        assert result.plan_hash is not None

    def test_approve_from_init_raises_error(self) -> None:
        """approve from INIT without pending_approval raises InvalidCommand."""
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
    """Tests for reject command.

    Updated for Phase 2: reject() requires pending_approval=True.
    """

    def test_reject_from_response_stage_halts_workflow(self) -> None:
        """reject from RESPONSE stage with pending_approval keeps state, stores feedback."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            pending_approval=True,  # Required for Phase 2
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        result = orchestrator.reject("test-session", feedback="Needs more detail")

        # State stays the same, feedback stored
        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.RESPONSE
        assert result.approval_feedback == "Needs more detail"
        assert result.pending_approval is False  # Resolved by reject

    def test_reject_without_pending_approval_raises_error(self) -> None:
        """reject without pending_approval raises InvalidCommand."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=False,  # No pending approval
        )
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
    """Tests for state persistence.

    Updated for Phase 2: approve() requires pending_approval=True.
    """

    def test_commands_save_state_after_transition(self) -> None:
        """Commands save state after successful transition."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=True,  # Required for Phase 2
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with patch.object(orchestrator, "_execute_action"):
            orchestrator.approve("test-session")

        store.save.assert_called()


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
        """Transitioning to COMPLETE sets status to SUCCESS.

        Updated for Phase 2: approve() requires pending_approval=True.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
            pending_approval=True,  # Required for Phase 2
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
            approval_config=_skip_approval_config(),
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


class TestPromptRejectionHandling:
    """Tests for PROMPT stage rejection behavior (ADR-0015).

    Updated for Phase 2: Uses _run_gate_after_action directly.
    """

    def test_prompt_rejection_skips_retry_loop(self, tmp_path: Path) -> None:
        """PROMPT rejection does not enter retry loop.

        Phase 2: Gates run via _run_gate_after_action.
        """
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
        from aiwf.domain.providers.ai_approval_provider import AIApprovalProvider
        from aiwf.domain.profiles.profile_factory import ProfileFactory

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Original prompt")

        # Configure AI approver that rejects
        config = ApprovalConfig(
            default_approver="claude-code",
            default_max_retries=3,  # Would normally retry
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock profile that doesn't support prompt regeneration
        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": False}

        # Mock the approval gate to return rejection
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(ProfileFactory, "create", return_value=mock_profile):
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback="Prompt needs more detail",
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # Should NOT have called _action_retry (that's for RESPONSE stage)
        # Should pause workflow with feedback
        assert state.approval_feedback == "Prompt needs more detail"
        assert state.retry_count == 1
        # Should NOT be in ERROR state (retry loop wasn't entered)
        assert state.status != WorkflowStatus.ERROR

    def test_prompt_rejection_applies_suggested_content(self, tmp_path: Path) -> None:
        """PROMPT rejection with allow_rewrite applies suggested content to file.

        Phase 2: Gates run via _run_gate_after_action.
        """
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        prompt_path = iteration_dir / "planning-prompt.md"
        prompt_path.write_text("# Original prompt")

        # Configure with allow_rewrite
        config = ApprovalConfig(
            stages={
                "plan.prompt": {
                    "approver": "claude-code",
                    "allow_rewrite": True,
                },
            }
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock the approval gate to return rejection with suggested content
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.return_value = ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Prompt needs more detail",
                suggested_content="# Improved prompt\n\nWith better details.",
            )

            orchestrator._run_gate_after_action(state, session_dir)

        # Verify suggested content was written to file
        assert prompt_path.read_text() == "# Improved prompt\n\nWith better details."

    def test_prompt_rejection_without_allow_rewrite_preserves_file(self, tmp_path: Path) -> None:
        """PROMPT rejection without allow_rewrite does not modify file.

        Phase 2: Gates run via _run_gate_after_action.
        """
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
        from aiwf.domain.profiles.profile_factory import ProfileFactory

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        prompt_path = iteration_dir / "planning-prompt.md"
        prompt_path.write_text("# Original prompt")

        # Configure without allow_rewrite (default is False)
        config = ApprovalConfig(default_approver="claude-code")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock profile that doesn't support prompt regeneration
        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": False}

        # Mock the approval gate to return rejection with suggested content
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(ProfileFactory, "create", return_value=mock_profile):
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback="Prompt needs more detail",
                    suggested_content="# This should NOT be applied",
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # File should be unchanged
        assert prompt_path.read_text() == "# Original prompt"


# ============================================================================
# Phase 2: Automatic Gate Execution Tests (ADR-0015 redesign)
# ============================================================================


class TestGateAfterAction:
    """Tests for automatic gate execution after content creation."""

    def test_approved_result_auto_continues(self, tmp_path: Path) -> None:
        """APPROVED result triggers automatic transition to next stage."""
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        # Create prompt file for approval
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Plan prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        # Mock approval gate to return APPROVED
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(orchestrator, "_auto_continue") as mock_auto:
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.APPROVED
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # Should auto-continue
        mock_auto.assert_called_once()
        # pending_approval should be False
        assert state.pending_approval is False

    def test_pending_result_sets_flag_and_pauses(self, tmp_path: Path) -> None:
        """PENDING result sets pending_approval and does NOT transition."""
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Plan prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        # Mock approval gate to return PENDING
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(orchestrator, "_auto_continue") as mock_auto:
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.PENDING,
                    feedback="Awaiting manual approval",
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # Should NOT auto-continue
        mock_auto.assert_not_called()
        # pending_approval should be True
        assert state.pending_approval is True
        # State saved
        store.save.assert_called()

    def test_rejected_result_triggers_retry_logic(self, tmp_path: Path) -> None:
        """REJECTED result triggers existing retry/rejection handling."""
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
        from aiwf.domain.profiles.profile_factory import ProfileFactory

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Plan prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        # Mock profile that doesn't support prompt regeneration
        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": False}

        # Mock approval gate to return REJECTED
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(ProfileFactory, "create", return_value=mock_profile):
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback="Needs more detail",
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # approval_feedback should be set
        assert state.approval_feedback == "Needs more detail"

    def test_gate_error_is_recoverable(self, tmp_path: Path) -> None:
        """Gate errors don't crash workflow - state saved for retry."""
        from aiwf.domain.errors import ProviderError

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Plan prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        # Mock approval gate to raise error
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.side_effect = ProviderError("Connection failed")

            orchestrator._run_gate_after_action(state, session_dir)

        # last_error should be set
        assert "Connection failed" in state.last_error
        # pending_approval should be False (error, not pending)
        assert state.pending_approval is False
        # State saved
        store.save.assert_called()

    def test_stageless_state_skips_gate(self, tmp_path: Path) -> None:
        """States without stage (INIT, terminal) skip gate."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.INIT, stage=None)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            orchestrator._run_gate_after_action(state, session_dir)

        # Gate should not be called for stageless states
        mock_gate.assert_not_called()


class TestAutoContinue:
    """Tests for automatic continuation after approval."""

    def test_auto_continue_advances_stage(self, tmp_path: Path) -> None:
        """Auto-continue transitions from PROMPT to RESPONSE."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with patch.object(orchestrator, "_execute_action"):
            orchestrator._auto_continue(state, session_dir)

        # Stage should transition to RESPONSE
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

    def test_auto_continue_executes_next_action(self, tmp_path: Path) -> None:
        """Auto-continue executes the action for the new stage."""
        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with patch.object(orchestrator, "_execute_action") as mock_action:
            orchestrator._auto_continue(state, session_dir)

        # _execute_action should be called
        mock_action.assert_called_once()


class TestGateIntegration:
    """Tests for gate integration into _execute_action."""

    def test_create_prompt_triggers_gate(self, tmp_path: Path) -> None:
        """CREATE_PROMPT action triggers approval gate."""
        from aiwf.application.transitions import Action
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.PROMPT)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        # Mock the prompt creation and gate
        with patch.object(orchestrator, "_action_create_prompt"):
            with patch.object(orchestrator, "_run_gate_after_action") as mock_gate:
                orchestrator._execute_action(state, Action.CREATE_PROMPT, "test-session")

        # Gate should be called after prompt creation
        mock_gate.assert_called_once()

    def test_call_ai_triggers_gate(self, tmp_path: Path) -> None:
        """CALL_AI action triggers approval gate."""
        from aiwf.application.transitions import Action
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision

        store = Mock(spec=SessionStore)
        state = _make_state(phase=WorkflowPhase.PLAN, stage=WorkflowStage.RESPONSE)
        store.load.return_value = state

        session_dir = tmp_path / "test-session"

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        # Mock the AI call and gate
        with patch.object(orchestrator, "_action_call_ai"):
            with patch.object(orchestrator, "_run_gate_after_action") as mock_gate:
                orchestrator._execute_action(state, Action.CALL_AI, "test-session")

        # Gate should be called after AI response
        mock_gate.assert_called_once()


class TestApproveCommandRedesigned:
    """Tests for approve command with new pending-resolution semantics."""

    def test_approve_resolves_pending(self, tmp_path: Path) -> None:
        """approve command resolves pending_approval and continues."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=True,
        )
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Plan prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with patch.object(orchestrator, "_auto_continue"):
            result = orchestrator.approve("test-session")

        # pending_approval should be resolved
        assert result.pending_approval is False

    def test_approve_without_pending_is_error(self) -> None:
        """approve command without pending_approval raises error."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=False,
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with pytest.raises(InvalidCommand) as exc_info:
            orchestrator.approve("test-session")

        assert "No pending approval" in str(exc_info.value)

    def test_approve_with_error_retries_gate(self, tmp_path: Path) -> None:
        """approve after gate error retries the gate."""
        from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision

        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            last_error="Previous gate error",
        )
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Plan prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with patch.object(orchestrator, "_run_gate_after_action") as mock_gate:
            result = orchestrator.approve("test-session")

        # Gate should be re-run
        mock_gate.assert_called_once()
        # Error should be cleared
        assert result.last_error is None


class TestRejectCommandRedesigned:
    """Tests for reject command with new pending-only semantics."""

    def test_reject_resolves_pending_with_feedback(self, tmp_path: Path) -> None:
        """reject command resolves pending and stores feedback."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=True,
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        result = orchestrator.reject("test-session", feedback="Needs more detail")

        # pending_approval should be resolved
        assert result.pending_approval is False
        # Feedback should be stored
        assert result.approval_feedback == "Needs more detail"

    def test_reject_without_pending_is_error(self) -> None:
        """reject command without pending_approval raises error."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=False,
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp/sessions"),
        )

        with pytest.raises(InvalidCommand) as exc_info:
            orchestrator.reject("test-session", feedback="Bad")

        assert "No pending approval" in str(exc_info.value)
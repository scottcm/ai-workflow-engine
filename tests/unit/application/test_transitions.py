"""Tests for TransitionTable state machine.

TDD Tests for ADR-0012 Phase 2.
Table-driven tests covering all valid transitions and invalid command rejection.
"""

import pytest

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.application.transitions import TransitionTable, TransitionResult, Action


class TestTransitionTableValidTransitions:
    """Tests for valid state transitions."""

    @pytest.mark.parametrize(
        "phase,stage,command,expected_phase,expected_stage,expected_action",
        [
            # === INIT transitions ===
            # init command starts workflow at PLAN[PROMPT]
            (WorkflowPhase.INIT, None, "init", WorkflowPhase.PLAN, WorkflowStage.PROMPT, Action.CREATE_PROMPT),

            # === PLAN phase transitions ===
            # PLAN[PROMPT] -> approve -> PLAN[RESPONSE] (AI called)
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "approve", WorkflowPhase.PLAN, WorkflowStage.RESPONSE, Action.CALL_AI),
            # PLAN[RESPONSE] -> approve -> GENERATE[PROMPT]
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE, "approve", WorkflowPhase.GENERATE, WorkflowStage.PROMPT, Action.CREATE_PROMPT),
            # PLAN[RESPONSE] -> reject -> stay (halt)
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE, "reject", WorkflowPhase.PLAN, WorkflowStage.RESPONSE, Action.HALT),

            # === GENERATE phase transitions ===
            # GENERATE[PROMPT] -> approve -> GENERATE[RESPONSE] (AI called)
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT, "approve", WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, Action.CALL_AI),
            # GENERATE[RESPONSE] -> approve -> REVIEW[PROMPT]
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, "approve", WorkflowPhase.REVIEW, WorkflowStage.PROMPT, Action.CREATE_PROMPT),
            # GENERATE[RESPONSE] -> reject -> stay (halt)
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, "reject", WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, Action.HALT),

            # === REVIEW phase transitions ===
            # REVIEW[PROMPT] -> approve -> REVIEW[RESPONSE] (AI called)
            (WorkflowPhase.REVIEW, WorkflowStage.PROMPT, "approve", WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, Action.CALL_AI),
            # REVIEW[RESPONSE] -> reject -> stay (halt)
            (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "reject", WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, Action.HALT),

            # === REVISE phase transitions ===
            # REVISE[PROMPT] -> approve -> REVISE[RESPONSE] (AI called)
            (WorkflowPhase.REVISE, WorkflowStage.PROMPT, "approve", WorkflowPhase.REVISE, WorkflowStage.RESPONSE, Action.CALL_AI),
            # REVISE[RESPONSE] -> approve -> REVIEW[PROMPT] (back to review)
            (WorkflowPhase.REVISE, WorkflowStage.RESPONSE, "approve", WorkflowPhase.REVIEW, WorkflowStage.PROMPT, Action.CREATE_PROMPT),
            # REVISE[RESPONSE] -> reject -> stay (halt)
            (WorkflowPhase.REVISE, WorkflowStage.RESPONSE, "reject", WorkflowPhase.REVISE, WorkflowStage.RESPONSE, Action.HALT),
        ],
    )
    def test_valid_transition(
        self,
        phase: WorkflowPhase,
        stage: WorkflowStage | None,
        command: str,
        expected_phase: WorkflowPhase,
        expected_stage: WorkflowStage | None,
        expected_action: Action,
    ) -> None:
        """Valid transitions return correct next state and action."""
        result = TransitionTable.get_transition(phase, stage, command)

        assert result is not None
        assert result.phase == expected_phase
        assert result.stage == expected_stage
        assert result.action == expected_action


class TestReviewResponseSpecialCase:
    """Tests for REVIEW[RESPONSE] special handling.

    REVIEW[RESPONSE] is special because the verdict determines next phase:
    - approve (no flags) -> engine checks verdict -> COMPLETE or REVISE[PROMPT]
    - approve --complete -> force COMPLETE
    - approve --revise -> force REVISE[PROMPT]

    The TransitionTable returns a special action for plain approve,
    and explicit transitions for the override flags.
    """

    def test_review_response_approve_returns_check_verdict_action(self) -> None:
        """Plain approve at REVIEW[RESPONSE] returns CHECK_VERDICT action."""
        result = TransitionTable.get_transition(
            WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve"
        )

        assert result is not None
        assert result.action == Action.CHECK_VERDICT
        # Phase/stage are placeholders; engine determines actual based on verdict
        assert result.phase == WorkflowPhase.REVIEW
        assert result.stage == WorkflowStage.RESPONSE

    def test_review_response_approve_complete_forces_complete(self) -> None:
        """approve --complete at REVIEW[RESPONSE] forces COMPLETE."""
        result = TransitionTable.get_transition(
            WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve_complete"
        )

        assert result is not None
        assert result.phase == WorkflowPhase.COMPLETE
        assert result.stage is None
        assert result.action == Action.FINALIZE

    def test_review_response_approve_revise_forces_revise(self) -> None:
        """approve --revise at REVIEW[RESPONSE] forces REVISE."""
        result = TransitionTable.get_transition(
            WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve_revise"
        )

        assert result is not None
        assert result.phase == WorkflowPhase.REVISE
        assert result.stage == WorkflowStage.PROMPT
        assert result.action == Action.CREATE_PROMPT


class TestCancelTransitions:
    """Tests for cancel command from any active state."""

    @pytest.mark.parametrize(
        "phase,stage",
        [
            (WorkflowPhase.INIT, None),
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT),
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE),
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT),
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE),
            (WorkflowPhase.REVIEW, WorkflowStage.PROMPT),
            (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE),
            (WorkflowPhase.REVISE, WorkflowStage.PROMPT),
            (WorkflowPhase.REVISE, WorkflowStage.RESPONSE),
        ],
    )
    def test_cancel_from_active_state(
        self, phase: WorkflowPhase, stage: WorkflowStage | None
    ) -> None:
        """Cancel from any active state transitions to CANCELLED."""
        result = TransitionTable.get_transition(phase, stage, "cancel")

        assert result is not None
        assert result.phase == WorkflowPhase.CANCELLED
        assert result.stage is None
        assert result.action == Action.CANCEL


class TestInvalidTransitions:
    """Tests for invalid command rejection."""

    @pytest.mark.parametrize(
        "phase,stage,command",
        [
            # Can't approve/reject from INIT
            (WorkflowPhase.INIT, None, "approve"),
            (WorkflowPhase.INIT, None, "reject"),
            # Can't reject from PROMPT stages (only from RESPONSE)
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "reject"),
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT, "reject"),
            (WorkflowPhase.REVIEW, WorkflowStage.PROMPT, "reject"),
            (WorkflowPhase.REVISE, WorkflowStage.PROMPT, "reject"),
            # Can't init from anywhere but INIT
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "init"),
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE, "init"),
            # Can't do anything from terminal states (comprehensive)
            (WorkflowPhase.COMPLETE, None, "approve"),
            (WorkflowPhase.COMPLETE, None, "init"),
            (WorkflowPhase.COMPLETE, None, "reject"),
            (WorkflowPhase.COMPLETE, None, "cancel"),
            (WorkflowPhase.ERROR, None, "approve"),
            (WorkflowPhase.ERROR, None, "init"),
            (WorkflowPhase.ERROR, None, "reject"),
            (WorkflowPhase.ERROR, None, "cancel"),
            (WorkflowPhase.CANCELLED, None, "approve"),
            (WorkflowPhase.CANCELLED, None, "init"),
            (WorkflowPhase.CANCELLED, None, "reject"),
            (WorkflowPhase.CANCELLED, None, "cancel"),
            # Unknown commands
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "unknown"),
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "step"),  # step was removed
        ],
    )
    def test_invalid_transition_returns_none(
        self, phase: WorkflowPhase, stage: WorkflowStage | None, command: str
    ) -> None:
        """Invalid transitions return None."""
        result = TransitionTable.get_transition(phase, stage, command)
        assert result is None


class TestValidCommands:
    """Tests for valid_commands() helper."""

    def test_valid_commands_from_init(self) -> None:
        """INIT state only accepts init and cancel."""
        commands = TransitionTable.valid_commands(WorkflowPhase.INIT, None)
        assert set(commands) == {"init", "cancel"}

    def test_valid_commands_from_prompt_stage(self) -> None:
        """PROMPT stages accept approve and cancel."""
        commands = TransitionTable.valid_commands(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        assert set(commands) == {"approve", "cancel"}

    def test_valid_commands_from_response_stage(self) -> None:
        """RESPONSE stages accept approve, reject, and cancel."""
        commands = TransitionTable.valid_commands(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert set(commands) == {"approve", "reject", "cancel"}

    def test_valid_commands_from_review_response(self) -> None:
        """REVIEW[RESPONSE] also accepts approve_complete and approve_revise."""
        commands = TransitionTable.valid_commands(WorkflowPhase.REVIEW, WorkflowStage.RESPONSE)
        assert set(commands) == {"approve", "approve_complete", "approve_revise", "reject", "cancel"}

    def test_valid_commands_from_terminal_state(self) -> None:
        """Terminal states have no valid commands."""
        assert TransitionTable.valid_commands(WorkflowPhase.COMPLETE, None) == []
        assert TransitionTable.valid_commands(WorkflowPhase.ERROR, None) == []
        assert TransitionTable.valid_commands(WorkflowPhase.CANCELLED, None) == []


class TestTransitionResultModel:
    """Tests for TransitionResult data class."""

    def test_transition_result_fields(self) -> None:
        """TransitionResult has required fields."""
        result = TransitionResult(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            action=Action.CREATE_PROMPT,
        )

        assert result.phase == WorkflowPhase.PLAN
        assert result.stage == WorkflowStage.PROMPT
        assert result.action == Action.CREATE_PROMPT

    def test_transition_result_with_none_stage(self) -> None:
        """TransitionResult allows None stage for terminal states."""
        result = TransitionResult(
            phase=WorkflowPhase.COMPLETE,
            stage=None,
            action=Action.FINALIZE,
        )

        assert result.phase == WorkflowPhase.COMPLETE
        assert result.stage is None


class TestActionEnum:
    """Tests for Action enum values."""

    def test_action_values_exist(self) -> None:
        """All required action values exist."""
        assert Action.CREATE_PROMPT.value == "create_prompt"
        assert Action.CALL_AI.value == "call_ai"
        assert Action.CHECK_VERDICT.value == "check_verdict"
        assert Action.FINALIZE.value == "finalize"
        assert Action.HALT.value == "halt"
        assert Action.CANCEL.value == "cancel"

    def test_action_count(self) -> None:
        """Exactly 6 actions defined."""
        assert len(Action) == 6


class TestCheckVerdictExclusivity:
    """Tests that CHECK_VERDICT action is only used for REVIEW[RESPONSE]."""

    def test_check_verdict_only_from_review_response(self) -> None:
        """CHECK_VERDICT action is only returned for REVIEW[RESPONSE] approve."""
        # Collect all transitions that return CHECK_VERDICT
        check_verdict_transitions = []

        # Check all possible phase/stage/command combinations
        all_phases = list(WorkflowPhase)
        all_stages = [None, WorkflowStage.PROMPT, WorkflowStage.RESPONSE]
        all_commands = ["init", "approve", "reject", "cancel",
                        "approve_complete", "approve_revise"]

        for phase in all_phases:
            for stage in all_stages:
                for command in all_commands:
                    result = TransitionTable.get_transition(phase, stage, command)
                    if result is not None and result.action == Action.CHECK_VERDICT:
                        check_verdict_transitions.append((phase, stage, command))

        # Should only be REVIEW[RESPONSE] with approve command
        assert check_verdict_transitions == [
            (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve")
        ]
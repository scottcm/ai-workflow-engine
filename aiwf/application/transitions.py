"""Declarative state transitions for workflow phases and stages.

ADR-0012 Phase 2: TransitionTable provides explicit, table-driven state machine
for workflow transitions.

Key concepts:
- (phase, stage, command) -> TransitionResult
- Work happens AFTER entering the new stage
- REVIEW[RESPONSE] is special: verdict determines COMPLETE vs REVISE
"""

from dataclasses import dataclass
from enum import Enum

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


class Action(str, Enum):
    """Actions to execute during transitions.

    These describe WHAT happens after the transition, not during.
    """

    CREATE_PROMPT = "create_prompt"  # Profile creates prompt for the phase
    CALL_AI = "call_ai"              # AI provider generates response
    CHECK_VERDICT = "check_verdict"  # Engine checks review verdict (REVIEW[RESPONSE] only)
    FINALIZE = "finalize"            # Complete the workflow
    HALT = "halt"                    # Stop workflow (legacy, reject now handles regeneration)
    CANCEL = "cancel"                # User cancelled workflow


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Result of a state transition.

    Attributes:
        phase: Target workflow phase
        stage: Target workflow stage (None for terminal states)
        action: Action to execute after transition
    """

    phase: WorkflowPhase
    stage: WorkflowStage | None
    action: Action


# Type alias for transition table key
_TransitionKey = tuple[WorkflowPhase, WorkflowStage | None, str]


class TransitionTable:
    """Declarative state machine for workflow transitions.

    Maps (current_phase, current_stage, command) -> TransitionResult.

    Usage:
        result = TransitionTable.get_transition(phase, stage, command)
        if result is None:
            raise InvalidCommand(...)
        # Execute result.action, then update state to result.phase/stage
    """

    # The complete transition table
    # Key: (phase, stage, command)
    # Value: TransitionResult(next_phase, next_stage, action)
    _TRANSITIONS: dict[_TransitionKey, TransitionResult] = {
        # === INIT transitions ===
        (WorkflowPhase.INIT, None, "init"): TransitionResult(
            WorkflowPhase.PLAN, WorkflowStage.PROMPT, Action.CREATE_PROMPT
        ),
        (WorkflowPhase.INIT, None, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),

        # === PLAN phase transitions ===
        (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "approve"): TransitionResult(
            WorkflowPhase.PLAN, WorkflowStage.RESPONSE, Action.CALL_AI
        ),
        (WorkflowPhase.PLAN, WorkflowStage.PROMPT, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),
        (WorkflowPhase.PLAN, WorkflowStage.RESPONSE, "approve"): TransitionResult(
            WorkflowPhase.GENERATE, WorkflowStage.PROMPT, Action.CREATE_PROMPT
        ),
        (WorkflowPhase.PLAN, WorkflowStage.RESPONSE, "reject"): TransitionResult(
            WorkflowPhase.PLAN, WorkflowStage.RESPONSE, Action.HALT
        ),
        (WorkflowPhase.PLAN, WorkflowStage.RESPONSE, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),

        # === GENERATE phase transitions ===
        (WorkflowPhase.GENERATE, WorkflowStage.PROMPT, "approve"): TransitionResult(
            WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, Action.CALL_AI
        ),
        (WorkflowPhase.GENERATE, WorkflowStage.PROMPT, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),
        (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, "approve"): TransitionResult(
            WorkflowPhase.REVIEW, WorkflowStage.PROMPT, Action.CREATE_PROMPT
        ),
        (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, "reject"): TransitionResult(
            WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, Action.HALT
        ),
        (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),

        # === REVIEW phase transitions ===
        (WorkflowPhase.REVIEW, WorkflowStage.PROMPT, "approve"): TransitionResult(
            WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, Action.CALL_AI
        ),
        (WorkflowPhase.REVIEW, WorkflowStage.PROMPT, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),
        # REVIEW[RESPONSE] is special - plain approve checks verdict
        (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve"): TransitionResult(
            WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, Action.CHECK_VERDICT
        ),
        # Override flags for when user disagrees with verdict
        (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve_complete"): TransitionResult(
            WorkflowPhase.COMPLETE, None, Action.FINALIZE
        ),
        (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "approve_revise"): TransitionResult(
            WorkflowPhase.REVISE, WorkflowStage.PROMPT, Action.CREATE_PROMPT
        ),
        (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "reject"): TransitionResult(
            WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, Action.HALT
        ),
        (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),

        # === REVISE phase transitions ===
        (WorkflowPhase.REVISE, WorkflowStage.PROMPT, "approve"): TransitionResult(
            WorkflowPhase.REVISE, WorkflowStage.RESPONSE, Action.CALL_AI
        ),
        (WorkflowPhase.REVISE, WorkflowStage.PROMPT, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),
        (WorkflowPhase.REVISE, WorkflowStage.RESPONSE, "approve"): TransitionResult(
            WorkflowPhase.REVIEW, WorkflowStage.PROMPT, Action.CREATE_PROMPT
        ),
        (WorkflowPhase.REVISE, WorkflowStage.RESPONSE, "reject"): TransitionResult(
            WorkflowPhase.REVISE, WorkflowStage.RESPONSE, Action.HALT
        ),
        (WorkflowPhase.REVISE, WorkflowStage.RESPONSE, "cancel"): TransitionResult(
            WorkflowPhase.CANCELLED, None, Action.CANCEL
        ),
    }

    @classmethod
    def get_transition(
        cls,
        phase: WorkflowPhase,
        stage: WorkflowStage | None,
        command: str,
    ) -> TransitionResult | None:
        """Get the transition result for a command from current state.

        Args:
            phase: Current workflow phase
            stage: Current workflow stage (None for INIT/terminal)
            command: Command to execute

        Returns:
            TransitionResult if valid, None if invalid command
        """
        return cls._TRANSITIONS.get((phase, stage, command))

    @classmethod
    def valid_commands(
        cls,
        phase: WorkflowPhase,
        stage: WorkflowStage | None,
    ) -> list[str]:
        """Get list of valid commands from current state.

        Args:
            phase: Current workflow phase
            stage: Current workflow stage

        Returns:
            List of command strings valid from this state
        """
        return [
            cmd
            for (p, s, cmd) in cls._TRANSITIONS
            if p == phase and s == stage
        ]
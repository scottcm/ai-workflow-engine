"""ActionDispatcher - maps Action enum to orchestrator methods.

During Phase 1, the dispatcher delegates to orchestrator methods to maintain
backward compatibility with tests. This will be refactored in later phases
to use executor classes directly.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from aiwf.application.transitions import Action
from aiwf.domain.models.workflow_state import WorkflowState

from .base import ActionContext

if TYPE_CHECKING:
    from aiwf.application.workflow_orchestrator import WorkflowOrchestrator


class ActionDispatcher:
    """Dispatches actions to orchestrator methods.

    For Phase 1, delegates to orchestrator._action_* methods to maintain
    backward compatibility with existing tests. The post-action approval
    gate for CREATE_PROMPT and CALL_AI is called after the action.
    """

    def dispatch(
        self,
        action: Action,
        state: WorkflowState,
        session_dir: Path,
        context: ActionContext,
    ) -> None:
        """Dispatch an action to the appropriate orchestrator method.

        Args:
            action: Action to execute
            state: Current workflow state
            session_dir: Path to session directory
            context: Action context with orchestrator reference

        Raises:
            ValueError: If action has no handler
        """
        orchestrator = context.orchestrator

        if action == Action.HALT:
            # No action needed - workflow is halted
            return

        if action == Action.CANCEL:
            # Cancel is handled by orchestrator directly
            return

        # Delegate to orchestrator methods for backward compatibility
        if action == Action.CREATE_PROMPT:
            orchestrator._action_create_prompt(state, session_dir)
        elif action == Action.CALL_AI:
            orchestrator._action_call_ai(state, session_dir)
        elif action == Action.CHECK_VERDICT:
            orchestrator._action_check_verdict(state, session_dir)
        elif action == Action.FINALIZE:
            orchestrator._action_finalize(state, session_dir)
        else:
            raise ValueError(f"No handler for action: {action}")

        # Run approval gate after CREATE_PROMPT and CALL_AI
        if action in (Action.CREATE_PROMPT, Action.CALL_AI):
            orchestrator._run_gate_after_action(state, session_dir)
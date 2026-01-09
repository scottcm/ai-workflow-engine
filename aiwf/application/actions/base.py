"""Base protocol and context for action executors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState

if TYPE_CHECKING:
    from aiwf.application.workflow_orchestrator import WorkflowOrchestrator


@dataclass
class ActionContext:
    """Context passed to action executors.

    Bundles orchestrator helpers and configuration needed by executors.
    This allows executors to be tested in isolation with mock context.
    """

    # Phase-to-filename mapping (from orchestrator)
    phase_files: dict[WorkflowPhase, tuple[str, str]]

    # Helper callbacks (bound to orchestrator instance)
    add_message: Callable[[WorkflowState, str], None]
    build_provider_context: Callable[[WorkflowState], dict[str, Any]]
    copy_plan_to_session: Callable[[WorkflowState, Path], None]
    run_gate_after_action: Callable[[WorkflowState, Path], None]

    # Reference to orchestrator for complex actions that need it
    # (e.g., check_verdict calls create_prompt)
    orchestrator: "WorkflowOrchestrator"


class ActionExecutor(ABC):
    """Protocol for action executors.

    Each executor handles one type of action in the workflow.
    Executors receive state and session_dir, plus context with helpers.
    """

    @abstractmethod
    def execute(
        self,
        state: WorkflowState,
        session_dir: Path,
        context: ActionContext,
    ) -> None:
        """Execute the action.

        Args:
            state: Current workflow state (may be mutated)
            session_dir: Path to session directory
            context: Action context with helpers and configuration
        """
        ...
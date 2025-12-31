"""Workflow orchestration using TransitionTable state machine.

ADR-0012 Phase 5: Engine-owned workflow orchestration with explicit transitions.
"""

import uuid
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiwf.application.context_validation import validate_context
from aiwf.application.standards_materializer import materialize_standards
from aiwf.application.transitions import Action, TransitionTable, TransitionResult

from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.errors import ProviderError
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.providers.provider_factory import ProviderFactory
from aiwf.domain.validation.path_validator import normalize_metadata_paths

if TYPE_CHECKING:
    from aiwf.domain.events.emitter import WorkflowEventEmitter
    from aiwf.domain.events.event_types import WorkflowEventType


class InvalidCommand(Exception):
    """Raised when a command is not valid for the current state."""

    def __init__(self, command: str, phase: WorkflowPhase, stage: WorkflowStage | None):
        self.command = command
        self.phase = phase
        self.stage = stage
        stage_str = f"[{stage.value}]" if stage else ""
        super().__init__(
            f"Command '{command}' is not valid from {phase.value}{stage_str}"
        )


@dataclass
class WorkflowOrchestrator:
    """Engine-owned workflow orchestration.

    This orchestrator owns deterministic phase transitions and persistence of
    `WorkflowState`. Profiles remain responsible for generating prompts and
    processing LLM responses; the orchestrator decides what happens next.

    ADR-0012: Uses TransitionTable for explicit, table-driven state machine.
    """

    session_store: SessionStore
    sessions_root: Path
    event_emitter: "WorkflowEventEmitter | None" = None

    def __post_init__(self) -> None:
        if self.event_emitter is None:
            from aiwf.domain.events.emitter import WorkflowEventEmitter
            self.event_emitter = WorkflowEventEmitter()

    # ========================================================================
    # Command Methods (ADR-0012)
    # ========================================================================

    def init(self, session_id: str) -> WorkflowState:
        """Start workflow from INIT phase.

        Transitions from INIT to PLAN[PROMPT] and executes CREATE_PROMPT action.

        Args:
            session_id: The session to initialize

        Returns:
            Updated workflow state

        Raises:
            InvalidCommand: If not in INIT phase
        """
        return self._execute_command(session_id, "init")

    def approve(
        self,
        session_id: str,
        hash_prompts: bool = False,
        fs_ability: str | None = None,
    ) -> WorkflowState:
        """Approve current stage and advance workflow.

        Args:
            session_id: The session to approve
            hash_prompts: Whether to hash prompt files (legacy, ignored)
            fs_ability: Resolved filesystem capability (legacy, ignored)

        Returns:
            Updated workflow state

        Raises:
            InvalidCommand: If approve is not valid from current state
        """
        return self._execute_command(session_id, "approve")

    def reject(self, session_id: str, feedback: str) -> WorkflowState:
        """Reject current content with feedback.

        Only valid from RESPONSE stages. Halts workflow until retry or cancel.

        Args:
            session_id: The session to reject
            feedback: Explanation of why content was rejected

        Returns:
            Updated workflow state (unchanged phase/stage, stores feedback)

        Raises:
            InvalidCommand: If reject is not valid from current state
        """
        state = self.session_store.load(session_id)
        state.messages = []

        transition = TransitionTable.get_transition(state.phase, state.stage, "reject")
        if transition is None:
            raise InvalidCommand("reject", state.phase, state.stage)

        # Store feedback for retrieval
        state.approval_feedback = feedback

        # State stays the same (HALT action)
        self.session_store.save(state)
        return state

    def retry(self, session_id: str, feedback: str) -> WorkflowState:
        """Retry current phase with feedback.

        Transitions back to PROMPT stage to regenerate with feedback.

        Args:
            session_id: The session to retry
            feedback: Feedback for regeneration

        Returns:
            Updated workflow state

        Raises:
            InvalidCommand: If retry is not valid from current state
        """
        state = self.session_store.load(session_id)
        state.messages = []

        transition = TransitionTable.get_transition(state.phase, state.stage, "retry")
        if transition is None:
            raise InvalidCommand("retry", state.phase, state.stage)

        # Store feedback for prompt regeneration
        state.approval_feedback = feedback

        # Execute the retry action
        self._execute_action(state, transition.action, session_id)

        # Update state
        state.phase = transition.phase
        state.stage = transition.stage

        self.session_store.save(state)
        return state

    def cancel(self, session_id: str) -> WorkflowState:
        """Cancel workflow.

        Valid from any active state. Transitions to CANCELLED.

        Args:
            session_id: The session to cancel

        Returns:
            Updated workflow state

        Raises:
            InvalidCommand: If cancel is not valid (e.g., already terminal)
        """
        state = self.session_store.load(session_id)
        state.messages = []

        transition = TransitionTable.get_transition(state.phase, state.stage, "cancel")
        if transition is None:
            raise InvalidCommand("cancel", state.phase, state.stage)

        # Update state
        state.phase = transition.phase
        state.stage = transition.stage
        state.status = WorkflowStatus.CANCELLED

        self.session_store.save(state)
        return state

    # ========================================================================
    # Legacy step() method - deprecated
    # ========================================================================

    def step(self, session_id: str) -> WorkflowState:
        """DEPRECATED - Use init() instead.

        The step command was removed in ADR-0012.
        Use init() to start workflow from INIT phase.
        """
        # For backwards compatibility, treat step from INIT as init
        state = self.session_store.load(session_id)
        if state.phase == WorkflowPhase.INIT:
            return self.init(session_id)

        # Otherwise, step is no longer valid
        raise InvalidCommand("step", state.phase, state.stage)

    # ========================================================================
    # Internal Methods
    # ========================================================================

    def _execute_command(self, session_id: str, command: str) -> WorkflowState:
        """Execute a command using the TransitionTable.

        Args:
            session_id: The session to operate on
            command: Command to execute

        Returns:
            Updated workflow state

        Raises:
            InvalidCommand: If command is not valid from current state
        """
        state = self.session_store.load(session_id)
        state.messages = []

        transition = TransitionTable.get_transition(state.phase, state.stage, command)
        if transition is None:
            raise InvalidCommand(command, state.phase, state.stage)

        # Execute the action
        self._execute_action(state, transition.action, session_id)

        # Update state
        state.phase = transition.phase
        state.stage = transition.stage

        # Update status for terminal states
        if state.phase == WorkflowPhase.COMPLETE:
            state.status = WorkflowStatus.SUCCESS
        elif state.phase == WorkflowPhase.CANCELLED:
            state.status = WorkflowStatus.CANCELLED
        elif state.phase == WorkflowPhase.ERROR:
            state.status = WorkflowStatus.ERROR

        self.session_store.save(state)
        return state

    def _execute_action(
        self,
        state: WorkflowState,
        action: Action,
        session_id: str,
    ) -> None:
        """Execute an action after transition.

        Actions describe WHAT happens after entering a new state.
        This method performs the actual work.

        Args:
            state: Current workflow state
            action: Action to execute
            session_id: Session identifier
        """
        session_dir = self.sessions_root / session_id

        if action == Action.CREATE_PROMPT:
            self._action_create_prompt(state, session_dir)
        elif action == Action.CALL_AI:
            self._action_call_ai(state, session_dir)
        elif action == Action.CHECK_VERDICT:
            self._action_check_verdict(state, session_dir)
        elif action == Action.FINALIZE:
            self._action_finalize(state, session_dir)
        elif action == Action.HALT:
            # No action needed - workflow is halted
            pass
        elif action == Action.RETRY:
            self._action_retry(state, session_dir)
        elif action == Action.CANCEL:
            # No action needed - state update handles it
            pass

    def _action_create_prompt(self, state: WorkflowState, session_dir: Path) -> None:
        """Create prompt file for current phase.

        Called when entering a PROMPT stage.
        """
        # TODO: Implement prompt creation using profile
        self._add_message(state, f"Creating {state.phase.value} prompt")

    def _action_call_ai(self, state: WorkflowState, session_dir: Path) -> None:
        """Call AI provider to generate response.

        Called when entering a RESPONSE stage.
        """
        # TODO: Implement AI call using provider
        self._add_message(state, f"Calling AI for {state.phase.value}")

    def _action_check_verdict(self, state: WorkflowState, session_dir: Path) -> None:
        """Check review verdict to determine next state.

        Only called from REVIEW[RESPONSE]. Determines COMPLETE vs REVISE.
        """
        # TODO: Implement verdict checking using profile
        self._add_message(state, "Checking review verdict")

    def _action_finalize(self, state: WorkflowState, session_dir: Path) -> None:
        """Finalize workflow completion."""
        self._add_message(state, "Workflow complete")

    def _action_retry(self, state: WorkflowState, session_dir: Path) -> None:
        """Prepare for retry with feedback."""
        self._add_message(state, f"Retrying {state.phase.value} with feedback")

    # ========================================================================
    # Session Initialization
    # ========================================================================

    def initialize_run(
        self,
        *,
        profile: str,
        providers: dict[str, str],
        context: dict[str, Any] | None = None,
        execution_mode: ExecutionMode = ExecutionMode.INTERACTIVE,
        metadata: dict[str, Any] | None = None,
        standards_provider: str | None = None,
        # Legacy parameters for backward compatibility
        scope: str | None = None,
        entity: str | None = None,
        bounded_context: str | None = None,
        table: str | None = None,
        dev: str | None = None,
        task_id: str | None = None,
    ) -> str:
        """Initialize a new workflow session and persist the initial state.

        Creates a new session identifier and persists an initial `WorkflowState`
        with:
        - phase = WorkflowPhase.INIT
        - status = WorkflowStatus.IN_PROGRESS
        - phase_history containing the initial (phase, status) entry

        This method MUST NOT create any `iteration-*` directories. Session
        directory creation may be performed by the configured `SessionStore`
        implementation as part of persistence.

        Args:
            profile: Profile identifier (e.g., "jpa-mt")
            providers: Role to provider mapping (e.g., {"planner": "manual"})
            context: Profile-specific context dict (new API)
            execution_mode: Interactive or automated execution
            metadata: Optional additional metadata
            standards_provider: Optional standards provider key override
            scope: (Legacy) Workflow scope - use context instead
            entity: (Legacy) Entity name - use context instead
            bounded_context: (Legacy) Bounded context name - use context instead
            table: (Legacy) Database table name - use context instead
            dev: (Legacy) Developer identifier - use context instead
            task_id: (Legacy) Task/ticket identifier - use context instead

        Returns:
            The generated session_id for the new workflow session.
        """
        session_id = uuid.uuid4().hex
        session_dir = self.sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Build context from either new context param or legacy params
        if context is not None:
            effective_context = dict(context)
        else:
            effective_context = {}
            if scope is not None:
                effective_context["scope"] = scope
            if entity is not None:
                effective_context["entity"] = entity
            if table is not None:
                effective_context["table"] = table
            if bounded_context is not None:
                effective_context["bounded_context"] = bounded_context
            if dev is not None:
                effective_context["dev"] = dev
            if task_id is not None:
                effective_context["task_id"] = task_id

        # Normalize paths in metadata
        metadata = normalize_metadata_paths(metadata)

        # Merge schema_file from metadata into context if present
        if metadata and "schema_file" in metadata:
            effective_context["schema_file"] = metadata["schema_file"]

        # Check if profile is registered
        if not ProfileFactory.is_registered(profile):
            shutil.rmtree(session_dir, ignore_errors=True)
            raise ValueError(f"Unknown profile: {profile}")

        # Validate context against profile schema
        profile_metadata = ProfileFactory.get_metadata(profile) or {}
        context_schema = profile_metadata.get("context_schema", {})
        validation_errors = validate_context(context_schema, effective_context)
        if validation_errors:
            shutil.rmtree(session_dir, ignore_errors=True)
            error_details = "; ".join(f"{e.field}: {e.message}" for e in validation_errors)
            raise ValueError(f"Context validation failed: {error_details}")

        state = _build_initial_state(
            session_id=session_id,
            profile=profile,
            context=effective_context,
            providers=providers,
            execution_mode=execution_mode,
            metadata=metadata,
        )

        # Validate all configured AI providers before continuing setup
        try:
            for role, provider_key in providers.items():
                ai_provider = ProviderFactory.create(provider_key)
                ai_provider.validate()
        except (KeyError, ProviderError):
            shutil.rmtree(session_dir, ignore_errors=True)
            raise

        profile_instance = ProfileFactory.create(profile)
        profile_instance.validate_metadata(metadata)

        # Resolve standards provider: CLI > profile default
        resolved_standards_provider = standards_provider
        if not resolved_standards_provider:
            resolved_standards_provider = (
                profile_instance.get_default_standards_provider_key()
            )

        # Create and validate standards provider
        try:
            from aiwf.domain.standards import StandardsProviderFactory

            standards_config = profile_instance.get_standards_config()
            sp = StandardsProviderFactory.create(
                resolved_standards_provider, standards_config
            )
            sp.validate()
            state.standards_provider = resolved_standards_provider
        except (KeyError, ProviderError):
            shutil.rmtree(session_dir, ignore_errors=True)
            raise

        standards_context = self._build_context(state)
        bundle_hash = materialize_standards(
            session_dir=session_dir,
            context=standards_context,
            provider=sp,
        )
        state.standards_hash = bundle_hash
        self.session_store.save(state)

        return session_id

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _add_message(self, state: WorkflowState, message: str) -> None:
        """Add a progress message to the state."""
        state.messages.append(message)

    def _build_context(self, state: WorkflowState) -> dict[str, Any]:
        """Extract context dict from workflow state for providers."""
        return {
            **state.context,
            "metadata": state.metadata,
        }

    def _emit(
        self,
        event_type: "WorkflowEventType",
        state: WorkflowState,
        **kwargs: Any,
    ) -> None:
        """Emit a workflow event with common fields."""
        from aiwf.domain.events.event import WorkflowEvent

        self.event_emitter.emit(
            WorkflowEvent(
                event_type=event_type,
                session_id=state.session_id,
                timestamp=datetime.now(timezone.utc),
                phase=state.phase,
                iteration=state.current_iteration,
                **kwargs,
            )
        )


def _build_initial_state(
    *,
    session_id: str,
    profile: str,
    context: dict[str, Any],
    providers: dict[str, str],
    execution_mode: ExecutionMode,
    metadata: dict[str, Any] | None,
) -> WorkflowState:
    """Build the initial `WorkflowState` for a new session.

    Initializes the workflow in:
    - phase = WorkflowPhase.INIT
    - status = WorkflowStatus.IN_PROGRESS
    and seeds `phase_history` with the initial (phase, status) entry.

    This function does not perform any I/O and does not create directories.

    Returns:
        A fully-populated `WorkflowState` instance representing the start of a run.
    """
    initial_phase = WorkflowPhase.INIT
    initial_status = WorkflowStatus.IN_PROGRESS

    return WorkflowState(
        session_id=session_id,
        profile=profile,
        context=context,
        providers=providers,
        execution_mode=execution_mode,
        metadata=metadata or {},
        phase=initial_phase,
        status=initial_status,
        standards_hash="0" * 64,
        phase_history=[PhaseTransition(phase=initial_phase, status=initial_status)],
    )
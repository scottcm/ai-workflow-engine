import uuid
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiwf.application.approval_handler import build_approval_chain
from aiwf.application.context_validation import validate_context
from aiwf.application.standards_materializer import materialize_standards

from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
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


@dataclass
class WorkflowOrchestrator:
    """Engine-owned workflow orchestration.

    This orchestrator owns deterministic phase transitions and persistence of
    `WorkflowState`. Profiles remain responsible for generating prompts and
    processing LLM responses; the orchestrator decides what happens next.
    """

    session_store: SessionStore
    sessions_root: Path
    event_emitter: "WorkflowEventEmitter | None" = None

    def __post_init__(self) -> None:
        self._approval_chain = build_approval_chain()
        if self.event_emitter is None:
            from aiwf.domain.events.emitter import WorkflowEventEmitter

            self.event_emitter = WorkflowEventEmitter()

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
            # New API: use context directly
            effective_context = dict(context)
        else:
            # Legacy API: build context from individual params
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
        # Clean up session directory if validation fails
        try:
            for role, provider_key in providers.items():
                ai_provider = ProviderFactory.create(provider_key)
                ai_provider.validate()  # Raises ProviderError if misconfigured
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

    def approve(
        self,
        session_id: str,
        hash_prompts: bool = False,
        fs_ability: str | None = None,
    ) -> WorkflowState:
        """STUB - Will be replaced by TransitionTable in Phase 5.

        ADR-0012 redesigns the workflow engine. This method is stubbed
        during the transition period.

        Args:
            session_id: The session to approve
            hash_prompts: Whether to hash prompt files
            fs_ability: Resolved filesystem capability

        Returns:
            The current workflow state (unchanged during transition).
        """
        state = self.session_store.load(session_id)
        state.messages = []
        # STUB: No approvals during ADR-0012 transition
        return state

    def _add_message(self, state: WorkflowState, message: str) -> None:
        """Add a progress message to the state."""
        state.messages.append(message)

    def _add_phase_message(self, state: WorkflowState) -> None:
        """Add phase transition message."""
        self._add_message(state, f"Advancing to {state.phase.name} phase")

    def _emit(
        self,
        event_type: "WorkflowEventType",
        state: WorkflowState,
        **kwargs: Any,
    ) -> None:
        """Emit a workflow event with common fields."""
        from aiwf.domain.events.event import WorkflowEvent
        from aiwf.domain.events.event_types import WorkflowEventType

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

    def step(self, session_id: str) -> WorkflowState:
        """STUB - Will be replaced by TransitionTable in Phase 5.

        ADR-0012 redesigns the workflow engine. This method is stubbed
        during the transition period.

        Args:
            session_id: Identifier of the workflow session to advance.

        Returns:
            The current workflow state (unchanged during transition).
        """
        state = self.session_store.load(session_id)
        state.messages = []
        # STUB: No transitions during ADR-0012 transition
        return state

    def _build_context(self, state: WorkflowState) -> dict[str, Any]:
        """Extract context dict from workflow state for providers."""
        return {
            **state.context,
            "metadata": state.metadata,
        }

    # NOTE: Legacy _step_* methods removed during ADR-0012 transition.
    # Will be replaced by TransitionTable in Phase 5.



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
"""Workflow orchestration using TransitionTable state machine.

ADR-0012 Phase 5: Engine-owned workflow orchestration with explicit transitions.
"""

import uuid
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from aiwf.application.context_validation import validate_context
from aiwf.application.standards_materializer import materialize_standards
from aiwf.application.transitions import Action, TransitionTable, TransitionResult

from aiwf.domain.models.workflow_state import (
    PhaseTransition,
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.errors import ProviderError
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.providers.provider_factory import AIProviderFactory
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.approval_factory import ApprovalProviderFactory
from aiwf.domain.models.approval_result import (
    ApprovalDecision,
    ApprovalResult,
    validate_approval_result,
)
from aiwf.application.approval_config import ApprovalConfig
from aiwf.domain.validation.path_validator import normalize_metadata_paths
from aiwf.domain.models.prompt_sections import PromptSections
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.application.actions import ActionDispatcher, ActionContext
from aiwf.application.approval import (
    ApprovalGateService,
    GateContext,
    _RegenerationNotImplemented,
)
from aiwf.application.providers import ProviderExecutionService
from aiwf.application.prompts import PromptService
from aiwf.application.artifacts import ArtifactService

if TYPE_CHECKING:
    from aiwf.domain.events.emitter import WorkflowEventEmitter
    from aiwf.domain.events.event_types import WorkflowEventType


class InvalidCommand(Exception):
    """Raised when a command is not valid for the current state."""

    def __init__(
        self,
        command: str,
        phase: WorkflowPhase,
        stage: WorkflowStage | None,
        message: str | None = None,
    ):
        self.command = command
        self.phase = phase
        self.stage = stage
        if message:
            super().__init__(message)
        else:
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
    ADR-0015: Integrates ApprovalProvider system for approval gates.
    """

    session_store: SessionStore
    sessions_root: Path
    event_emitter: "WorkflowEventEmitter | None" = None
    approval_config: ApprovalConfig = field(default_factory=ApprovalConfig)

    # Phase-to-filename mapping (DRY: single source of truth)
    _PHASE_FILES: ClassVar[dict[WorkflowPhase, tuple[str, str]]] = {
        WorkflowPhase.PLAN: ("planning-prompt.md", "planning-response.md"),
        WorkflowPhase.GENERATE: ("generation-prompt.md", "generation-response.md"),
        WorkflowPhase.REVIEW: ("review-prompt.md", "review-response.md"),
        WorkflowPhase.REVISE: ("revision-prompt.md", "revision-response.md"),
    }

    # Action dispatcher for executing workflow actions
    _action_dispatcher: ActionDispatcher = field(default_factory=ActionDispatcher, repr=False)

    # Approval gate service for handling approval gates
    _approval_gate_service: ApprovalGateService = field(default_factory=ApprovalGateService, repr=False)

    # Provider execution service for AI provider calls
    _provider_service: ProviderExecutionService = field(default_factory=ProviderExecutionService, repr=False)

    # Prompt generation service
    _prompt_service: PromptService = field(default_factory=PromptService, repr=False)

    # Artifact service for pre-transition approval handling
    _artifact_service: ArtifactService = field(default_factory=ArtifactService, repr=False)

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
        """Resolve a pending approval and continue workflow.

        Only valid when:
        - pending_approval is True (resolves the pending state)
        - last_error is set (retries failed gate)

        Args:
            session_id: The session to approve
            hash_prompts: Whether to hash prompt files (legacy, ignored)
            fs_ability: Resolved filesystem capability (legacy, ignored)

        Returns:
            Updated workflow state

        Raises:
            InvalidCommand: If no pending approval to resolve
        """
        state = self.session_store.load(session_id)
        state.messages = []
        session_dir = self.sessions_root / session_id

        # Check if there's something to resolve
        if not state.pending_approval and not state.last_error:
            raise InvalidCommand(
                "approve",
                state.phase,
                state.stage,
                f"No pending approval to resolve. "
                f"Current state: {state.phase.value}[{state.stage.value if state.stage else 'none'}]. "
                f"Gates run automatically after content creation. "
                f"Use 'status' to see current workflow state.",
            )

        # Clear error state if retrying after error
        if state.last_error:
            state.last_error = None
            self._run_gate_after_action(state, session_dir)
            return state

        # Resolve pending approval
        state.pending_approval = False
        self._clear_approval_state(state)
        self._handle_pre_transition_approval(state, session_dir)
        self._auto_continue(state, session_dir)

        return state

    def reject(self, session_id: str, feedback: str) -> WorkflowState:
        """Reject content and regenerate with feedback.

        At RESPONSE stage with AI provider: Regenerates response using same prompt + feedback.
        At PROMPT stage or manual provider: Stores feedback for manual intervention.

        Args:
            session_id: The session to reject
            feedback: Explanation of what to fix

        Returns:
            Updated workflow state (regenerated or paused for intervention)

        Raises:
            InvalidCommand: If no pending approval to reject
        """
        state = self.session_store.load(session_id)
        state.messages = []
        session_dir = self.sessions_root / session_id

        if not state.pending_approval:
            raise InvalidCommand(
                "reject",
                state.phase,
                state.stage,
                f"No pending approval to reject. "
                f"Current state: {state.phase.value}[{state.stage.value if state.stage else 'none'}]. "
                f"The 'reject' command is only valid when awaiting manual approval.",
            )

        state.approval_feedback = feedback
        self._add_message(state, f"Rejected: {feedback}")

        # At RESPONSE stage with AI provider: regenerate response
        if state.stage == WorkflowStage.RESPONSE:
            provider_key = self._get_provider_key_for_phase(state)
            if provider_key and provider_key != "manual":
                # Clear pending approval and regenerate
                state.pending_approval = False
                self._add_message(state, "Regenerating with feedback...")
                self._action_call_ai(state, session_dir)
                # After regeneration, set up for approval again
                state.pending_approval = True
                self.session_store.save(state)
                return state

        # For PROMPT stage or manual provider: pause for user intervention
        # Keep pending_approval True so user can approve after manual edits
        state.pending_approval = True
        self._add_message(state, "Awaiting manual intervention. Edit the file and run 'approve'.")

        self.session_store.save(state)
        return state

    def _get_provider_key_for_phase(self, state: WorkflowState) -> str | None:
        """Get the AI provider key for the current phase.

        Args:
            state: Current workflow state

        Returns:
            Provider key (e.g., 'claude-code', 'manual') or None
        """
        phase_to_role = {
            WorkflowPhase.PLAN: "planner",
            WorkflowPhase.GENERATE: "generator",
            WorkflowPhase.REVIEW: "reviewer",
            WorkflowPhase.REVISE: "revisor",
        }
        role = phase_to_role.get(state.phase)
        if role and state.ai_providers:
            return state.ai_providers.get(role)
        return None

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
        session_dir = self.sessions_root / session_id

        transition = TransitionTable.get_transition(state.phase, state.stage, command)
        if transition is None:
            raise InvalidCommand(command, state.phase, state.stage)

        # Update state BEFORE action - work happens AFTER entering new state (ADR-0012)
        state.phase = transition.phase
        state.stage = transition.stage

        # Execute the action after transition
        self._execute_action(state, transition.action, session_id)

        # Update status for terminal states
        if state.phase == WorkflowPhase.COMPLETE:
            state.status = WorkflowStatus.SUCCESS
        elif state.phase == WorkflowPhase.CANCELLED:
            state.status = WorkflowStatus.CANCELLED
        elif state.phase == WorkflowPhase.ERROR:
            state.status = WorkflowStatus.ERROR

        self.session_store.save(state)
        return state

    def _build_action_context(self, session_dir: Path) -> ActionContext:
        """Build ActionContext for executor dispatch.

        Args:
            session_dir: Session directory path

        Returns:
            ActionContext with helpers and configuration
        """
        return ActionContext(
            phase_files=self._PHASE_FILES,
            add_message=self._add_message,
            build_provider_context=self._build_provider_context,
            copy_plan_to_session=self._copy_plan_to_session,
            run_gate_after_action=self._run_gate_after_action,
            orchestrator=self,
        )

    def _build_gate_context(self, session_dir: Path) -> GateContext:
        """Build GateContext for approval gate service.

        Args:
            session_dir: Session directory path

        Returns:
            GateContext with helpers and configuration
        """
        return GateContext(
            phase_files=self._PHASE_FILES,
            approval_config=self.approval_config,
            add_message=self._add_message,
            build_base_context=self._build_base_context,
            build_provider_context=self._build_provider_context,
            get_approver=self._get_approver,
            save_state=self.session_store.save,
            action_retry=self._action_retry,
            execute_action=self._execute_action,
            handle_pre_transition_approval=self._handle_pre_transition_approval,
            write_regenerated_prompt=self._write_regenerated_prompt,
            # Gate method callbacks (allow test patching)
            run_approval_gate=self._run_approval_gate,
            handle_approval_rejection=self._handle_approval_rejection,
            handle_prompt_rejection=self._handle_prompt_rejection,
            handle_response_rejection=self._handle_response_rejection,
            clear_approval_state=self._clear_approval_state,
            auto_continue=self._auto_continue,
            orchestrator=self,
        )

    def _execute_action(
        self,
        state: WorkflowState,
        action: Action,
        session_id: str,
    ) -> None:
        """Execute an action after transition.

        Actions describe WHAT happens after entering a new state.
        Delegates to ActionDispatcher for execution.

        Args:
            state: Current workflow state
            action: Action to execute
            session_id: Session identifier
        """
        session_dir = self.sessions_root / session_id
        context = self._build_action_context(session_dir)
        self._action_dispatcher.dispatch(action, state, session_dir, context)

    def _action_create_prompt(self, state: WorkflowState, session_dir: Path) -> None:
        """Create prompt file for current phase.

        Called when entering a PROMPT stage.
        """
        # Phase-specific setup before creating the prompt
        if state.phase == WorkflowPhase.GENERATE:
            # Gate: plan must be approved before entering GENERATE
            if not state.plan_approved:
                raise ValueError("Cannot enter GENERATE phase: plan not approved")
            # Copy planning-response.md → plan.md (session-level artifact)
            self._copy_plan_to_session(state, session_dir)

        # Build context for prompt generation
        context = self._build_provider_context(state)

        # Generate prompt via service
        result = self._prompt_service.generate_prompt(
            state, session_dir, self._PHASE_FILES, context
        )

        # Create iteration directory if needed
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        # Write prompt file
        prompt_path = iteration_dir / result.prompt_filename
        prompt_path.write_text(result.user_prompt, encoding="utf-8")

        self._add_message(state, f"Created {result.prompt_filename}")

    def _action_call_ai(self, state: WorkflowState, session_dir: Path) -> None:
        """Call AI provider to generate response.

        Called when entering a RESPONSE stage.
        For manual provider (returns None), user provides response file externally.
        For automated providers, writes response file directly.
        """
        # Map phase to provider role
        phase_to_role = {
            WorkflowPhase.PLAN: "planner",
            WorkflowPhase.GENERATE: "generator",
            WorkflowPhase.REVIEW: "reviewer",
            WorkflowPhase.REVISE: "reviser",
        }
        role = phase_to_role.get(state.phase)
        if role is None:
            raise ValueError(f"No provider role for phase: {state.phase}")

        provider_key = state.ai_providers.get(role)
        if provider_key is None:
            raise ValueError(f"No provider configured for role: {role}")

        # Get filenames from class constant (DRY)
        prompt_filename, response_filename = self._PHASE_FILES[state.phase]

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        prompt_path = iteration_dir / prompt_filename
        response_path = iteration_dir / response_filename

        # Read prompt
        if not prompt_path.exists():
            raise ValueError(f"Prompt file not found: {prompt_path}")
        prompt_content = prompt_path.read_text(encoding="utf-8")

        # Build context for provider
        context = self._build_provider_context(state)
        context["prompt_filename"] = prompt_filename
        context["response_filename"] = response_filename

        # Execute via provider service
        try:
            result = self._provider_service.execute(
                provider_key, prompt_content, context=context
            )
        except ProviderError as e:
            state.last_error = str(e)
            state.status = WorkflowStatus.ERROR
            raise

        if result.awaiting_response:
            # Provider didn't generate response - user provides externally
            self._add_message(
                state,
                f"Awaiting {response_filename}"
            )
        else:
            # Handle result from automated provider
            # Check if provider already wrote the response file (local-write providers)
            response_path_str = str(response_path)
            provider_wrote_response = response_path_str in result.files

            if provider_wrote_response:
                # Provider wrote the file directly - don't overwrite with console output
                self._add_message(state, f"Created {response_filename}")
            elif result.response:
                # Provider returned content - write it
                response_path.write_text(result.response, encoding="utf-8")
                self._add_message(state, f"Created {response_filename}")
            # Handle files dict for code generation
            for file_path, content in result.files.items():
                if content is not None:
                    full_path = iteration_dir / "code" / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    self._add_message(state, f"Created code/{file_path}")

    def _action_check_verdict(self, state: WorkflowState, session_dir: Path) -> None:
        """Check review verdict to determine next state.

        Only called from REVIEW[RESPONSE]. Parses verdict and dynamically
        transitions to COMPLETE (PASS) or REVISE (FAIL).
        """
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "review-response.md"

        if not response_path.exists():
            raise ValueError(f"Review response not found: {response_path}")

        content = response_path.read_text(encoding="utf-8")

        # Use profile to process review response
        profile = ProfileFactory.create(state.profile)
        result = profile.process_review_response(content)

        # Extract verdict from result metadata
        verdict = result.metadata.get("verdict", "").upper()

        if verdict == "PASS":
            # Transition to COMPLETE
            state.phase = WorkflowPhase.COMPLETE
            state.stage = None
            state.status = WorkflowStatus.SUCCESS
            self._add_message(state, "Review verdict: PASS → workflow complete")
        elif verdict == "FAIL":
            # Transition to REVISE[PROMPT], increment iteration
            state.current_iteration += 1
            state.phase = WorkflowPhase.REVISE
            state.stage = WorkflowStage.PROMPT
            self._add_message(state, "Review verdict: FAIL → revision required")
            # Create revision prompt for new iteration
            self._action_create_prompt(state, session_dir)
            # Run gate to trigger auto-continue to REVISE[RESPONSE]
            self._run_gate_after_action(state, session_dir)
        else:
            # No valid verdict found - store error but continue
            state.last_error = f"Invalid or missing review verdict: '{verdict}'"
            self._add_message(state, f"Warning: Could not parse verdict from review response")

    def _action_finalize(self, state: WorkflowState, session_dir: Path) -> None:
        """Finalize workflow completion."""
        self._add_message(state, "Workflow complete")

    def _action_retry(self, state: WorkflowState, session_dir: Path) -> None:
        """Retry response generation with feedback.

        Called when user retries from RESPONSE stage. Stays at RESPONSE stage
        and regenerates the response using the same prompt + feedback context.
        """
        feedback = state.approval_feedback
        self._add_message(
            state,
            f"Retrying {state.phase.value}" + (" with feedback" if feedback else "")
        )
        # Regenerate the response - provider can use approval_feedback from context
        self._action_call_ai(state, session_dir)

    # ========================================================================
    # Session Initialization
    # ========================================================================

    def initialize_run(
        self,
        *,
        profile: str,
        providers: dict[str, str],
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        standards_provider: str | None = None,
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
            context: Profile-specific context dict
            metadata: Optional additional metadata
            standards_provider: Optional standards provider key override

        Returns:
            The generated session_id for the new workflow session.
        """
        session_id = uuid.uuid4().hex
        session_dir = self.sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        effective_context = dict(context) if context else {}

        # Merge dev and task_id into metadata if provided
        effective_metadata = dict(metadata) if metadata else {}
        if dev:
            effective_metadata["developer"] = dev
        if task_id:
            effective_metadata["task_id"] = task_id

        # Normalize paths in metadata
        metadata = normalize_metadata_paths(effective_metadata)

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
            metadata=metadata,
        )

        # Validate all configured AI providers before continuing setup
        try:
            for role, provider_key in providers.items():
                ai_provider = AIProviderFactory.create(provider_key)
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

        standards_context = self._build_provider_context(state)
        bundle_hash = materialize_standards(
            session_dir=session_dir,
            context=standards_context,
            provider=sp,
        )
        state.standards_hash = bundle_hash
        self.session_store.save(state)

        return session_id

    # ========================================================================
    # Approval Logic (delegated to ArtifactService)
    # ========================================================================

    def _handle_pre_transition_approval(
        self, state: WorkflowState, session_dir: Path
    ) -> None:
        """Handle approval logic BEFORE state transition.

        Delegates to ArtifactService for hashing and artifact creation.
        """
        self._artifact_service.handle_pre_transition_approval(
            state, session_dir, self._add_message
        )

    def _copy_plan_to_session(self, state: WorkflowState, session_dir: Path) -> None:
        """Copy planning-response.md to plan.md at session level.

        Called when entering GENERATE phase after plan is approved.
        Delegates to ArtifactService.
        """
        self._artifact_service.copy_plan_to_session(
            state, session_dir, self._add_message
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _add_message(self, state: WorkflowState, message: str) -> None:
        """Add a progress message to the state."""
        state.messages.append(message)

    def _build_base_context(self, state: WorkflowState) -> dict[str, Any]:
        """Base context shared by providers and approvers.

        ADR-0015: Single source of truth for shared context keys.
        """
        ctx = {
            **state.context,
            "session_id": state.session_id,
            "iteration": state.current_iteration,
            "metadata": state.metadata,
        }
        # Retry-related fields - always included when present
        if state.approval_feedback:
            ctx["approval_feedback"] = state.approval_feedback
        if state.suggested_content:
            ctx["suggested_content"] = state.suggested_content
        return ctx

    def _build_provider_context(self, state: WorkflowState) -> dict[str, Any]:
        """Context for response providers.

        Includes phase and stage so providers can determine their role
        without parsing prompt content.
        """
        ctx = self._build_base_context(state)
        ctx["phase"] = state.phase.value if state.phase else None
        ctx["stage"] = state.stage.value if state.stage else None
        return ctx

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

    # ========================================================================
    # Approval Gate Methods (ADR-0015)
    # ========================================================================

    def _get_approver(
        self,
        phase: WorkflowPhase,
        stage: WorkflowStage,
    ) -> ApprovalProvider:
        """Get approval provider for the given phase/stage.

        Args:
            phase: Workflow phase
            stage: Workflow stage

        Returns:
            ApprovalProvider instance
        """
        stage_config = self.approval_config.get_stage_config(phase.value, stage.value)
        return ApprovalProviderFactory.create(stage_config.approver)

    def _build_approval_files(
        self,
        state: WorkflowState,
        session_dir: Path,
    ) -> dict[str, str | None]:
        """Build files dict for approval evaluation.

        Returns dict of filepath -> content for files relevant to approval.
        Content is None if provider should read file directly (local-read capable).
        """
        files: dict[str, str | None] = {}

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"

        # Map phase/stage to relevant files
        phase_files = {
            (WorkflowPhase.PLAN, WorkflowStage.PROMPT): ["planning-prompt.md"],
            (WorkflowPhase.PLAN, WorkflowStage.RESPONSE): ["planning-response.md"],
            (WorkflowPhase.GENERATE, WorkflowStage.PROMPT): ["generation-prompt.md"],
            (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE): ["generation-response.md"],
            (WorkflowPhase.REVIEW, WorkflowStage.PROMPT): ["review-prompt.md"],
            (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE): ["review-response.md"],
            (WorkflowPhase.REVISE, WorkflowStage.PROMPT): ["revision-prompt.md"],
            (WorkflowPhase.REVISE, WorkflowStage.RESPONSE): ["revision-response.md", "revision-issues.md"],
        }

        file_names = phase_files.get((state.phase, state.stage), [])

        for name in file_names:
            file_path = iteration_dir / name
            if file_path.exists():
                # Read content for the approver
                files[str(file_path)] = file_path.read_text(encoding="utf-8")
            else:
                files[str(file_path)] = None

        # Add code files for GENERATE[RESPONSE] and REVISE[RESPONSE]
        if state.stage == WorkflowStage.RESPONSE and state.phase in (
            WorkflowPhase.GENERATE,
            WorkflowPhase.REVISE,
        ):
            code_dir = iteration_dir / "code"
            if code_dir.exists():
                for code_file in code_dir.rglob("*"):
                    if code_file.is_file():
                        files[str(code_file)] = code_file.read_text(encoding="utf-8")

        # Add plan.md for GENERATE and REVIEW phases
        if state.phase in (WorkflowPhase.GENERATE, WorkflowPhase.REVIEW):
            plan_path = session_dir / "plan.md"
            if plan_path.exists():
                files[str(plan_path)] = plan_path.read_text(encoding="utf-8")

        return files

    def _build_approval_context(
        self,
        state: WorkflowState,
        session_dir: Path,
    ) -> dict[str, Any]:
        """Context for approval providers - extends base with approval-specific keys.

        ADR-0015: Uses base context builder to prevent drift.
        """
        ctx = self._build_base_context(state)
        stage_config = self.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )
        ctx.update({
            "allow_rewrite": stage_config.allow_rewrite,
            "session_dir": str(session_dir),
            "plan_file": str(session_dir / "plan.md"),
        })
        return ctx

    def _run_gate_after_action(
        self,
        state: WorkflowState,
        session_dir: Path,
    ) -> None:
        """Run approval gate after content creation and handle result.

        Called automatically after CREATE_PROMPT and CALL_AI actions.
        Delegates to ApprovalGateService for the actual gate logic.

        Args:
            state: Current workflow state (modified in place)
            session_dir: Session directory path
        """
        context = self._build_gate_context(session_dir)
        self._approval_gate_service.run_after_action(state, session_dir, context)

    def _auto_continue(
        self,
        state: WorkflowState,
        session_dir: Path,
    ) -> None:
        """Automatically continue to next stage after approval.

        Performs the state transition and executes the next action.
        If the next action also passes approval, continues recursively
        (enabling fully automated workflows with skip/AI approvers).

        Args:
            state: Current workflow state
            session_dir: Session directory path
        """
        # Get transition for approve command (same as manual approve)
        transition = TransitionTable.get_transition(state.phase, state.stage, "approve")
        if transition is None:
            return  # No valid transition (shouldn't happen)

        # Update state BEFORE action (ADR-0012)
        state.phase = transition.phase
        state.stage = transition.stage

        # Update status for terminal states
        if state.phase == WorkflowPhase.COMPLETE:
            state.status = WorkflowStatus.SUCCESS
        elif state.phase == WorkflowPhase.CANCELLED:
            state.status = WorkflowStatus.CANCELLED
        elif state.phase == WorkflowPhase.ERROR:
            state.status = WorkflowStatus.ERROR

        # Execute the action for new state
        self._execute_action(state, transition.action, state.session_id)

        # Save state
        self.session_store.save(state)

    def _run_approval_gate(
        self,
        state: WorkflowState,
        session_dir: Path,
    ) -> ApprovalResult:
        """Run approval gate for current phase/stage.

        Args:
            state: Current workflow state
            session_dir: Session directory path

        Returns:
            ApprovalResult (never None - PENDING replaces None for manual approval)
        """
        if state.stage is None:
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        approver = self._get_approver(state.phase, state.stage)

        # Build files and context
        files = self._build_approval_files(state, session_dir)
        context = self._build_approval_context(state, session_dir)

        # Run approval
        result = approver.evaluate(
            phase=state.phase,
            stage=state.stage,
            files=files,
            context=context,
        )

        return result

    def _handle_approval_rejection(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
    ) -> WorkflowState | None:
        """Handle approval rejection by dispatching to stage-specific handler.

        Returns None if retry succeeded (caller should proceed with transition).
        Returns state if workflow should pause.

        Args:
            state: Current workflow state
            session_dir: Session directory
            result: The rejection result

        Returns:
            Updated workflow state, or None if retry succeeded
        """
        # Store rejection info in state
        state.approval_feedback = result.feedback
        state.retry_count += 1

        if state.stage == WorkflowStage.PROMPT:
            return self._handle_prompt_rejection(state, session_dir, result)
        else:
            return self._handle_response_rejection(state, session_dir, result)

    def _handle_prompt_rejection(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
    ) -> WorkflowState | None:
        """Handle rejection during PROMPT stage.

        Attempts suggested_content application or profile regeneration.
        Falls back to pausing for user review/edit.

        Returns None if retry succeeded, state if paused.
        """
        stage_config = self.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )

        # Try suggested_content if available and allowed
        if result.suggested_content and stage_config.allow_rewrite:
            self._apply_suggested_content_to_prompt(state, session_dir, result.suggested_content)
            state.pending_approval = True  # User should review and approve
            self._add_message(state, "Suggested content applied to prompt file")
            self.session_store.save(state)
            return state

        # Try profile regeneration if supported
        profile = ProfileFactory.create(state.profile)
        if profile.get_metadata().get("can_regenerate_prompts", False):
            try:
                regeneration_result = self._try_prompt_regeneration(state, session_dir, result)
                # None means success (proceed with transition) or NotImplementedError (fall through)
                # state means paused (pending or rejected after retry)
                return regeneration_result
            except _RegenerationNotImplemented:
                pass  # Fall through to user pause

        # Pause for user to review/edit and re-approve
        state.pending_approval = True
        self._add_message(state, f"Prompt rejected: {result.feedback or 'no feedback'}")
        self.session_store.save(state)
        return state

    def _try_prompt_regeneration(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
    ) -> WorkflowState | None:
        """Attempt to regenerate prompt using profile capability.

        Returns:
            None if regeneration approved (caller proceeds with transition)
            state if paused (pending or rejected)
            None if NotImplementedError (caller falls through to user pause)
        """
        profile = ProfileFactory.create(state.profile)
        try:
            context = self._build_provider_context(state)
            new_prompt = profile.regenerate_prompt(
                state.phase,
                result.feedback or "",
                context,
            )

            self._write_regenerated_prompt(state, session_dir, new_prompt)
            self._add_message(state, "Prompt regenerated based on feedback")

            new_result = self._run_approval_gate(state, session_dir)

            if new_result.decision == ApprovalDecision.PENDING:
                state.pending_approval = True
                self.session_store.save(state)
                return state

            if new_result.decision == ApprovalDecision.APPROVED:
                return None  # Proceed with transition

            # Still rejected - recurse
            return self._handle_approval_rejection(state, session_dir, new_result)

        except NotImplementedError:
            # Profile declared capability but didn't implement
            raise _RegenerationNotImplemented()

    def _handle_response_rejection(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
    ) -> WorkflowState | None:
        """Handle rejection during RESPONSE stage with retry loop.

        Auto-retries up to max_retries using AI regeneration.
        Returns None if retry succeeded, state if paused.
        """
        stage_config = self.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )

        # Store suggested_content if available
        if result.suggested_content and stage_config.allow_rewrite:
            state.suggested_content = result.suggested_content
            self._add_message(state, "Suggested content available (not auto-applied yet)")

        # Retry loop - only for stages with max_retries > 0
        while state.retry_count <= stage_config.max_retries and stage_config.max_retries > 0:
            self._add_message(
                state,
                f"Retry {state.retry_count}/{stage_config.max_retries}: regenerating with feedback"
            )

            self._action_retry(state, session_dir)
            new_result = self._run_approval_gate(state, session_dir)

            if new_result.decision == ApprovalDecision.PENDING:
                state.pending_approval = True
                self.session_store.save(state)
                return state

            if new_result.decision == ApprovalDecision.APPROVED:
                return None  # Proceed with transition

            # Still rejected - update and continue loop
            state.approval_feedback = new_result.feedback
            state.retry_count += 1

        # Max retries exceeded - pause for human intervention
        if state.retry_count > stage_config.max_retries and stage_config.max_retries > 0:
            state.last_error = (
                f"Approval rejected after {state.retry_count} attempts. "
                "Review feedback and retry manually or cancel."
            )
            self._add_message(
                state, "Approval failed: max retries exceeded. Review feedback and retry or cancel."
            )

        # Pause workflow for human intervention
        state.pending_approval = True
        self.session_store.save(state)
        return state

    def _clear_approval_state(self, state: WorkflowState) -> None:
        """Clear approval tracking fields after successful approval."""
        state.approval_feedback = None
        state.suggested_content = None
        state.retry_count = 0

    def _apply_suggested_content_to_prompt(
        self,
        state: WorkflowState,
        session_dir: Path,
        suggested_content: str,
    ) -> None:
        """Apply suggested content to the prompt file.

        Called when a PROMPT stage is rejected with allow_rewrite=true
        and the approver provides suggested_content.

        Args:
            state: Current workflow state
            session_dir: Session directory
            suggested_content: The suggested prompt content to apply
        """
        # Get prompt filename from class constant (DRY)
        if state.phase not in self._PHASE_FILES:
            return

        prompt_filename = self._PHASE_FILES[state.phase][0]  # First element is prompt filename

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        prompt_path = iteration_dir / prompt_filename

        if prompt_path.exists():
            prompt_path.write_text(suggested_content, encoding="utf-8")

    def _write_regenerated_prompt(
        self,
        state: WorkflowState,
        session_dir: Path,
        prompt_content: str | PromptSections,
    ) -> None:
        """Write regenerated prompt content to prompt file.

        ADR-0015: Called when a profile regenerates a prompt based on rejection feedback.

        Args:
            state: Current workflow state
            session_dir: Session directory
            prompt_content: Regenerated prompt (string or PromptSections)
        """
        # Get filenames from class constant (DRY)
        prompt_filename, response_filename = self._PHASE_FILES.get(
            state.phase, ("prompt.md", "response.md")
        )

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        # Construct iteration-relative response path for output instructions
        response_relpath = f"iteration-{state.current_iteration}/{response_filename}"

        # Assemble prompt via service
        final_content = self._prompt_service.assemble_prompt(
            prompt_content, state, session_dir, response_relpath
        )

        # Write prompt file
        prompt_path = iteration_dir / prompt_filename
        prompt_path.write_text(final_content, encoding="utf-8")


def _build_initial_state(
    *,
    session_id: str,
    profile: str,
    context: dict[str, Any],
    providers: dict[str, str],
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
        ai_providers=providers,
        metadata=metadata or {},
        phase=initial_phase,
        status=initial_status,
        standards_hash="0" * 64,
        phase_history=[PhaseTransition(phase=initial_phase, status=initial_status)],
    )
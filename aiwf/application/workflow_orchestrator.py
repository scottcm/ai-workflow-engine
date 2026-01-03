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
from aiwf.domain.providers.provider_factory import ResponseProviderFactory
from aiwf.domain.providers.approval_provider import (
    ApprovalProvider,
    SkipApprovalProvider,
    ManualApprovalProvider,
)
from aiwf.domain.providers.approval_factory import ApprovalProviderFactory
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.application.approval_config import ApprovalConfig
from aiwf.domain.validation.path_validator import normalize_metadata_paths
from aiwf.domain.models.prompt_sections import PromptSections

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
    ADR-0015: Integrates ApprovalProvider system for approval gates.
    """

    session_store: SessionStore
    sessions_root: Path
    event_emitter: "WorkflowEventEmitter | None" = None
    approval_config: ApprovalConfig = field(default_factory=ApprovalConfig)

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
        """Retry response generation with feedback.

        Only valid from RESPONSE stages. Regenerates the response using the
        same prompt with feedback context available to the provider.

        Args:
            session_id: The session to retry
            feedback: Feedback for regeneration

        Returns:
            Updated workflow state (stays at RESPONSE stage with new response)

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
        session_dir = self.sessions_root / session_id

        transition = TransitionTable.get_transition(state.phase, state.stage, command)
        if transition is None:
            raise InvalidCommand(command, state.phase, state.stage)

        # ADR-0015: Run approval gate BEFORE hashing (gate must approve first)
        if command == "approve":
            # Check if this is a manual approver - user's approve command IS the approval
            approver = self._get_approver(state.phase, state.stage) if state.stage else None
            is_manual = isinstance(approver, ManualApprovalProvider)

            if is_manual:
                # Manual approval: user's approve command is the decision
                # No gate needed - clear state and proceed with transition
                self._clear_approval_state(state)
                self._handle_pre_transition_approval(state, session_dir)
            else:
                # AI/Skip approvers: run the gate
                try:
                    approval_result = self._run_approval_gate(state, session_dir)
                except (ProviderError, TimeoutError) as e:
                    # Approval gate failed - keep workflow recoverable
                    state.last_error = f"Approval gate error: {e}"
                    self._add_message(state, f"Approval failed: {e}. Retry with 'approve' or cancel.")
                    self.session_store.save(state)
                    return state

                if approval_result is None:
                    # This shouldn't happen for non-manual approvers, but handle gracefully
                    logger.warning("Non-manual approver returned None - treating as rejection")
                    self._add_message(state, "Approval provider returned no decision")
                    self.session_store.save(state)
                    return state

                if approval_result.decision == ApprovalDecision.REJECTED:
                    # Handle rejection (may retry for AI approvers)
                    # Returns None if retry succeeded (proceed with transition)
                    # Returns state if workflow should pause
                    rejection_result = self._handle_approval_rejection(state, session_dir, approval_result)
                    if rejection_result is not None:
                        return rejection_result
                    # Retry succeeded - fall through to continue with transition

                # Approved - clear any previous rejection state
                self._clear_approval_state(state)

                # Now hash and set flags AFTER approval gate passes
                self._handle_pre_transition_approval(state, session_dir)

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
        from aiwf.application.prompt_assembler import PromptAssembler

        # Phase-specific setup before creating the prompt
        if state.phase == WorkflowPhase.GENERATE:
            # Gate: plan must be approved before entering GENERATE
            if not state.plan_approved:
                raise ValueError("Cannot enter GENERATE phase: plan not approved")
            # Copy planning-response.md → plan.md (session-level artifact)
            self._copy_plan_to_session(state, session_dir)

        # Get profile instance
        profile = ProfileFactory.create(state.profile)

        # Build context from state
        context = self._build_provider_context(state)

        # Get phase-specific prompt from profile
        phase_prompt_methods = {
            WorkflowPhase.PLAN: profile.generate_planning_prompt,
            WorkflowPhase.GENERATE: profile.generate_generation_prompt,
            WorkflowPhase.REVIEW: profile.generate_review_prompt,
            WorkflowPhase.REVISE: profile.generate_revision_prompt,
        }

        if state.phase not in phase_prompt_methods:
            raise ValueError(f"No prompt generation for phase: {state.phase}")

        profile_prompt = phase_prompt_methods[state.phase](context)

        # Map phase to filenames
        phase_file_map = {
            WorkflowPhase.PLAN: ("planning-prompt.md", "planning-response.md"),
            WorkflowPhase.GENERATE: ("generation-prompt.md", "generation-response.md"),
            WorkflowPhase.REVIEW: ("review-prompt.md", "review-response.md"),
            WorkflowPhase.REVISE: ("revision-prompt.md", "revision-response.md"),
        }
        prompt_filename, response_filename = phase_file_map[state.phase]

        # Create iteration directory if needed
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        # Construct workspace-relative response path for output instructions
        # Uses forward slashes for cross-platform compatibility
        response_relpath = (
            f".aiwf/sessions/{state.session_id}/"
            f"iteration-{state.current_iteration}/{response_filename}"
        )

        # Assemble prompt: substitute engine variables, append output instructions
        assembler = PromptAssembler(session_dir, state)
        assembled = assembler.assemble(
            profile_prompt,
            fs_ability="local-write",
            response_relpath=response_relpath,
        )

        # Write prompt file
        prompt_path = iteration_dir / prompt_filename
        prompt_path.write_text(assembled["user_prompt"], encoding="utf-8")

        self._add_message(state, f"Created {prompt_filename}")

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

        provider_key = state.providers.get(role)
        if provider_key is None:
            raise ValueError(f"No provider configured for role: {role}")

        # Map phase to filenames
        phase_file_map = {
            WorkflowPhase.PLAN: ("planning-prompt.md", "planning-response.md"),
            WorkflowPhase.GENERATE: ("generation-prompt.md", "generation-response.md"),
            WorkflowPhase.REVIEW: ("review-prompt.md", "review-response.md"),
            WorkflowPhase.REVISE: ("revision-prompt.md", "revision-response.md"),
        }
        prompt_filename, response_filename = phase_file_map[state.phase]

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        prompt_path = iteration_dir / prompt_filename
        response_path = iteration_dir / response_filename

        # Read prompt
        if not prompt_path.exists():
            raise ValueError(f"Prompt file not found: {prompt_path}")
        prompt_content = prompt_path.read_text(encoding="utf-8")

        # Create provider and call
        provider = ResponseProviderFactory.create(provider_key)
        context = self._build_provider_context(state)

        try:
            response = provider.generate(prompt_content, context=context)
        except ProviderError as e:
            state.last_error = str(e)
            state.status = WorkflowStatus.ERROR
            raise

        if response is None:
            # Manual provider - user provides response externally
            self._add_message(
                state,
                f"Awaiting {response_filename} (manual provider)"
            )
        else:
            # Automated provider - write response file
            response_path.write_text(response, encoding="utf-8")
            self._add_message(state, f"Created {response_filename}")

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
                ai_provider = ResponseProviderFactory.create(provider_key)
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
    # Approval Logic (Double Dispatch Pattern)
    # ========================================================================

    # Dispatch table: (phase, stage) -> handler method name
    # Adding a new approval handler requires only:
    # 1. Add entry here
    # 2. Implement the _approve_* method
    _APPROVAL_HANDLERS: ClassVar[dict[tuple[WorkflowPhase, WorkflowStage | None], str]] = {
        (WorkflowPhase.PLAN, WorkflowStage.RESPONSE): "_approve_plan_response",
        (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE): "_approve_generate_response",
        (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE): "_approve_review_response",
        (WorkflowPhase.REVISE, WorkflowStage.RESPONSE): "_approve_revise_response",
    }

    def _handle_pre_transition_approval(
        self, state: WorkflowState, session_dir: Path
    ) -> None:
        """Handle approval logic BEFORE state transition.

        Uses double dispatch - looks up handler by (phase, stage) tuple.
        No if...elif chains; adding handlers only touches the dispatch table.
        """
        key = (state.phase, state.stage)
        handler_name = self._APPROVAL_HANDLERS.get(key)

        if handler_name is not None:
            handler = getattr(self, handler_name)
            handler(state, session_dir)

    def _approve_plan_response(self, state: WorkflowState, session_dir: Path) -> None:
        """Approve plan response: hash planning-response.md, set plan_approved."""
        import hashlib

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "planning-response.md"

        if response_path.exists():
            content = response_path.read_bytes()
            state.plan_hash = hashlib.sha256(content).hexdigest()
            state.plan_approved = True
            self._add_message(state, "Plan approved")
        else:
            raise ValueError(
                f"Cannot approve: planning-response.md not found at {response_path}"
            )

    def _approve_generate_response(self, state: WorkflowState, session_dir: Path) -> None:
        """Approve generation response: extract code, create artifacts."""
        from aiwf.domain.models.workflow_state import Artifact
        from aiwf.domain.validation.path_validator import PathValidator
        import hashlib

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "generation-response.md"

        if not response_path.exists():
            raise ValueError(f"Cannot approve: generation-response.md not found at {response_path}")

        content = response_path.read_text(encoding="utf-8")

        # Use profile to process and extract code
        profile = ProfileFactory.create(state.profile)
        result = profile.process_generation_response(content, session_dir, state.current_iteration)

        # Execute write plan if present
        if result.write_plan:
            code_dir = iteration_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)

            for write_op in result.write_plan.writes:
                # Validate and normalize path - profile returns filename-only or relative paths
                normalized_path = PathValidator.validate_artifact_path(write_op.path)

                # Write the file
                file_path = code_dir / normalized_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(write_op.content, encoding="utf-8")

                # Compute hash and create artifact
                file_hash = hashlib.sha256(write_op.content.encode("utf-8")).hexdigest()
                artifact = Artifact(
                    path=f"iteration-{state.current_iteration}/code/{normalized_path}",
                    phase=WorkflowPhase.GENERATE,
                    iteration=state.current_iteration,
                    sha256=file_hash,
                )
                state.artifacts.append(artifact)

            self._add_message(state, f"Extracted {len(result.write_plan.writes)} code file(s)")
        else:
            self._add_message(state, "Generation approved (no code extracted)")

    def _approve_review_response(self, state: WorkflowState, session_dir: Path) -> None:
        """Approve review response: hash review-response.md, set review_approved."""
        import hashlib

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "review-response.md"

        if response_path.exists():
            content = response_path.read_bytes()
            state.review_hash = hashlib.sha256(content).hexdigest()
            state.review_approved = True
            self._add_message(state, "Review approved")
        else:
            raise ValueError(
                f"Cannot approve: review-response.md not found at {response_path}"
            )

    def _approve_revise_response(self, state: WorkflowState, session_dir: Path) -> None:
        """Approve revision response: extract code, update artifacts."""
        from aiwf.domain.models.workflow_state import Artifact
        from aiwf.domain.validation.path_validator import PathValidator
        import hashlib

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "revision-response.md"

        if not response_path.exists():
            raise ValueError(f"Cannot approve: revision-response.md not found at {response_path}")

        content = response_path.read_text(encoding="utf-8")

        # Use profile to process and extract revised code
        profile = ProfileFactory.create(state.profile)
        result = profile.process_revision_response(content, session_dir, state.current_iteration)

        # Execute write plan if present
        if result.write_plan:
            code_dir = iteration_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)

            for write_op in result.write_plan.writes:
                # Validate and normalize path - profile returns filename-only or relative paths
                normalized_path = PathValidator.validate_artifact_path(write_op.path)

                # Write the file
                file_path = code_dir / normalized_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(write_op.content, encoding="utf-8")

                # Compute hash and create artifact for this iteration
                file_hash = hashlib.sha256(write_op.content.encode("utf-8")).hexdigest()
                artifact = Artifact(
                    path=f"iteration-{state.current_iteration}/code/{normalized_path}",
                    phase=WorkflowPhase.REVISE,
                    iteration=state.current_iteration,
                    sha256=file_hash,
                )
                state.artifacts.append(artifact)

            self._add_message(state, f"Extracted {len(result.write_plan.writes)} revised code file(s)")
        else:
            self._add_message(state, "Revision approved (no code extracted)")

    def _copy_plan_to_session(self, state: WorkflowState, session_dir: Path) -> None:
        """Copy planning-response.md to plan.md at session level.

        Called when entering GENERATE phase after plan is approved.
        """
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        source = iteration_dir / "planning-response.md"
        dest = session_dir / "plan.md"

        if not source.exists():
            raise ValueError(f"Cannot copy plan: {source} not found")

        shutil.copy2(source, dest)
        self._add_message(state, "Copied plan to session")

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
        """Context for response providers."""
        return self._build_base_context(state)

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

    def _run_approval_gate(
        self,
        state: WorkflowState,
        session_dir: Path,
    ) -> ApprovalResult | None:
        """Run approval gate for current phase/stage.

        Args:
            state: Current workflow state
            session_dir: Session directory path

        Returns:
            ApprovalResult if decision made, None if paused for manual approval
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
        """Handle approval rejection with iterative retry logic.

        Returns None if retry succeeded (caller should proceed with transition).
        Returns state if workflow should pause.

        For PROMPT stages: apply suggested_content if allow_rewrite, pause for user
        For RESPONSE stages with AI approvers: auto-retry up to max_retries
        For manual: store feedback, keep workflow paused

        Args:
            state: Current workflow state
            session_dir: Session directory
            result: The rejection result

        Returns:
            Updated workflow state
        """
        stage_config = self.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )

        # Store rejection info in state
        state.approval_feedback = result.feedback
        state.retry_count += 1

        # PROMPT stage: handle differently based on profile capability
        # ADR-0015: Check if profile can regenerate prompts on rejection
        if state.stage == WorkflowStage.PROMPT:
            # First, try suggested_content if available
            if result.suggested_content and stage_config.allow_rewrite:
                self._apply_suggested_content_to_prompt(state, session_dir, result.suggested_content)
                self._add_message(state, "Suggested content applied to prompt file")
                self.session_store.save(state)
                return state

            # Check if profile supports prompt regeneration
            profile = ProfileFactory.create(state.profile)
            profile_meta = profile.get_metadata()

            if profile_meta.get("can_regenerate_prompts", False):
                # Profile can regenerate prompts - attempt regeneration with feedback
                try:
                    context = self._build_provider_context(state)
                    new_prompt = profile.regenerate_prompt(
                        state.phase,
                        result.feedback or "",
                        context,
                    )

                    # Write regenerated prompt
                    self._write_regenerated_prompt(state, session_dir, new_prompt)
                    self._add_message(state, f"Prompt regenerated based on feedback")

                    # Re-run approval gate
                    new_result = self._run_approval_gate(state, session_dir)

                    if new_result is None:
                        # Manual approval pause
                        self.session_store.save(state)
                        return state

                    if new_result.decision == ApprovalDecision.APPROVED:
                        # Retry succeeded - return None to signal "proceed with transition"
                        # Don't save state here; caller will handle transition and save
                        return None

                    # Still rejected - continue with same handling (recursive call)
                    return self._handle_approval_rejection(state, session_dir, new_result)

                except NotImplementedError:
                    # Profile declared capability but didn't implement method
                    self._add_message(state, f"Prompt rejected: {result.feedback or 'no feedback'}")
            else:
                # Profile cannot regenerate - stay IN_PROGRESS for user
                self._add_message(state, f"Prompt rejected: {result.feedback or 'no feedback'}")

            # Pause for user to review/edit and re-approve
            self.session_store.save(state)
            return state

        # RESPONSE stage: handle suggested_content if allow_rewrite
        if result.suggested_content and stage_config.allow_rewrite:
            state.suggested_content = result.suggested_content
            # TODO: Apply suggestion to response file
            self._add_message(state, "Suggested content available (not auto-applied yet)")

        # Check if AI approver
        approver = self._get_approver(state.phase, state.stage)
        is_ai_approver = not isinstance(approver, (SkipApprovalProvider, ManualApprovalProvider))

        if is_ai_approver:
            # Iterative retry loop for AI approvers (RESPONSE stage only)
            while state.retry_count <= stage_config.max_retries:
                # Regenerate content with feedback
                self._add_message(
                    state,
                    f"Retry {state.retry_count}/{stage_config.max_retries}: regenerating with feedback"
                )

                # Store feedback for provider context and regenerate
                self._action_retry(state, session_dir)

                # Re-run approval gate
                new_result = self._run_approval_gate(state, session_dir)

                if new_result is None:
                    # Manual approval pause (shouldn't happen for AI approver)
                    break

                if new_result.decision == ApprovalDecision.APPROVED:
                    # Retry succeeded - return None to signal "proceed with transition"
                    # Don't save state here; caller will handle transition and save
                    return None

                # Still rejected - update state and continue loop
                state.approval_feedback = new_result.feedback
                state.retry_count += 1

            # Max retries exceeded - stay IN_PROGRESS for user intervention (ADR-0015)
            state.last_error = f"Approval rejected after {state.retry_count} attempts. Review feedback and retry manually or cancel."
            self._add_message(state, "Approval failed: max retries exceeded. Review feedback and retry or cancel.")

        # For manual approver or failed AI, save state and return
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
        # Map phase to prompt filename
        phase_prompt_map = {
            WorkflowPhase.PLAN: "planning-prompt.md",
            WorkflowPhase.GENERATE: "generation-prompt.md",
            WorkflowPhase.REVIEW: "review-prompt.md",
            WorkflowPhase.REVISE: "revision-prompt.md",
        }

        prompt_filename = phase_prompt_map.get(state.phase)
        if not prompt_filename:
            return

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
        from aiwf.application.prompt_assembler import PromptAssembler

        # Map phase to filenames
        phase_file_map = {
            WorkflowPhase.PLAN: ("planning-prompt.md", "planning-response.md"),
            WorkflowPhase.GENERATE: ("generation-prompt.md", "generation-response.md"),
            WorkflowPhase.REVIEW: ("review-prompt.md", "review-response.md"),
            WorkflowPhase.REVISE: ("revision-prompt.md", "revision-response.md"),
        }

        prompt_filename, response_filename = phase_file_map.get(
            state.phase, ("prompt.md", "response.md")
        )

        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        # Construct workspace-relative response path for output instructions
        response_relpath = (
            f".aiwf/sessions/{state.session_id}/"
            f"iteration-{state.current_iteration}/{response_filename}"
        )

        # Assemble prompt if it's PromptSections, otherwise use directly
        if isinstance(prompt_content, PromptSections):
            assembler = PromptAssembler(session_dir, state)
            assembled = assembler.assemble(
                prompt_content,
                fs_ability="local-write",
                response_relpath=response_relpath,
            )
            final_content = assembled["user_prompt"]
        else:
            final_content = prompt_content

        # Write prompt file
        prompt_path = iteration_dir / prompt_filename
        prompt_path.write_text(final_content, encoding="utf-8")


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
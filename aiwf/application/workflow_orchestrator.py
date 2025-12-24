import importlib
import uuid
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS
from aiwf.application.artifact_writer import write_artifacts
from aiwf.application.approval_handler import ApprovalHandler
from aiwf.application.standards_materializer import materialize_standards

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.validation.path_validator import normalize_metadata_paths


@dataclass
class WorkflowOrchestrator:
    """Engine-owned workflow orchestration.

    This orchestrator owns deterministic phase transitions and persistence of
    `WorkflowState`. Profiles remain responsible for generating prompts and
    processing LLM responses; the orchestrator decides what happens next.
    """

    session_store: SessionStore
    sessions_root: Path

    def initialize_run(
        self,
        *,
        profile: str,
        scope: str,
        entity: str,
        providers: dict[str, str],
        execution_mode: ExecutionMode = ExecutionMode.INTERACTIVE,
        bounded_context: str | None = None,
        table: str | None = None,
        dev: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Initialize a new workflow session and persist the initial state.

        Creates a new session identifier and persists an initial `WorkflowState`
        with:
        - phase = WorkflowPhase.INITIALIZED
        - status = WorkflowStatus.IN_PROGRESS
        - phase_history containing the initial (phase, status) entry

        This method MUST NOT create any `iteration-*` directories. Session
        directory creation may be performed by the configured `SessionStore`
        implementation as part of persistence.

        Returns:
            The generated session_id for the new workflow session.
        """
        session_id = uuid.uuid4().hex
        session_dir = self.sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        metadata = normalize_metadata_paths(metadata)

        state = _build_initial_state(
            session_id=session_id,
            profile=profile,
            scope=scope,
            entity=entity,
            providers=providers,
            execution_mode=execution_mode,
            bounded_context=bounded_context,
            table=table,
            dev=dev,
            task_id=task_id,
            metadata=metadata,
        )

        profile_instance = ProfileFactory.create(profile)
        profile_instance.validate_metadata(metadata)
        provider = profile_instance.get_standards_provider()

        context = self._build_context(state)
        bundle_hash = materialize_standards(
            session_dir=session_dir,
            context=context,
            provider=provider
        )
        state.standards_hash = bundle_hash
        self.session_store.save(state)

        return session_id

    def approve(self, session_id: str, hash_prompts: bool = False) -> WorkflowState:
        state = self.session_store.load(session_id)
        session_dir = self.sessions_root / session_id

        try:
            updated = ApprovalHandler().approve(
                session_dir=session_dir,
                state=state,
                hash_prompts=hash_prompts,
            )

            # Success is recovery: always reset status and clear any prior error.
            updated.status = WorkflowStatus.IN_PROGRESS
            updated.last_error = None

            self.session_store.save(updated)
            return updated

        except (FileNotFoundError, ValueError) as e:
            state.status = WorkflowStatus.ERROR
            state.last_error = str(e)
            self.session_store.save(state)
            return state

    def step(self, session_id: str) -> WorkflowState:
        """Advance the workflow by one deterministic unit of work.

        Loads the persisted `WorkflowState` for `session_id` and performs at most
        one phase transition per call. If required input artifacts are missing,
        the workflow is considered blocked and this method returns the current
        state unchanged without persisting.

        Prompt generation is combined with phase entry: when transitioning into
        an ING phase (PLANNING, GENERATING, REVIEWING, REVISING), the prompt
        file is generated immediately in the same step.

        Implemented transitions:
        - INITIALIZED -> PLANNING: generates planning-prompt.md
        - PLANNING -> PLANNED: when planning-response.md exists
        - PLANNED -> GENERATING: processes response, writes plan.md, creates
            iteration-1/, generates generation-prompt.md
        - GENERATING -> GENERATED: when generation-response.md exists and valid
        - GENERATED -> REVIEWING: gates on approved artifacts, generates review-prompt.md
        - REVIEWING -> REVIEWED: when review-response.md exists
        - REVIEWED:
            - SUCCESS   -> COMPLETE (status=SUCCESS)
            - FAILED    -> REVISING: increments iteration, creates dir, generates revision-prompt.md
            - ERROR     -> ERROR (status=ERROR)
            - CANCELLED -> CANCELLED (status=CANCELLED)
        - REVISING -> REVISED: when revision-response.md exists and valid
        - REVISED -> REVIEWING: gates on approved artifacts, generates review-prompt.md

        Args:
            session_id: Identifier of the workflow session to advance.

        Returns:
            The current workflow state after applying at most one unit of work.
        """
        state = self.session_store.load(session_id)

        if state.phase == WorkflowPhase.INITIALIZED:
            return self._step_initialized(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.PLANNING:
            return self._step_planning(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.PLANNED:
            return self._step_planned(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.GENERATING:
            return self._step_generating(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.GENERATED:
            return self._step_generated(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.REVIEWING:
            return self._step_reviewing(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.REVIEWED:
            return self._step_reviewed(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.REVISING:
            return self._step_revising(session_id=session_id, state=state)

        if state.phase == WorkflowPhase.REVISED:
            return self._step_revised(session_id=session_id, state=state)

        return state

    def _build_context(self, state: WorkflowState) -> dict[str, Any]:
        """Extract context dict from workflow state for providers."""
        return {
            "scope": state.scope,
            "entity": state.entity,
            "table": state.table,
            "bounded_context": state.bounded_context,
            "dev": state.dev,
            "task_id": state.task_id,
            "metadata": state.metadata,
        }

    def _step_initialized(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle INITIALIZED -> PLANNING.

        Transitions to PLANNING and immediately generates planning-prompt.md.
        """
        session_dir = self.sessions_root / session_id

        state.phase = WorkflowPhase.PLANNING
        state.status = WorkflowStatus.IN_PROGRESS
        self._append_phase_history(state, phase=state.phase, status=state.status)
        self.session_store.save(state)

        # Generate planning prompt immediately on entry
        spec = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING]
        prompt_rel = spec.prompt_relpath_template.format(N=state.current_iteration)
        prompt_file = session_dir / prompt_rel
        prompt_file.parent.mkdir(parents=True, exist_ok=True)

        profile_instance = ProfileFactory.create(state.profile)
        content = profile_instance.generate_planning_prompt(self._prompt_context(state=state))
        prompt_file.write_text(content, encoding="utf-8")

        return state

    def _step_planning(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle PLANNING phase logic.

        Prompt was generated on entry to PLANNING.
        Check if response exists and transition to PLANNED.
        """
        session_dir = self.sessions_root / session_id

        spec = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING]
        response_rel = spec.response_relpath_template.format(N=state.current_iteration)
        response_file = session_dir / response_rel

        if response_file.exists():
            state.phase = WorkflowPhase.PLANNED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        return state

    def _step_planned(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle PLANNED -> GENERATING.

        - Process planning-response.md.
        - If successful, write plan.md and create iteration-1/.
        """
        if not state.plan_approved:
            return state

        session_dir = self.sessions_root / session_id

        spec = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING]
        response_rel = spec.response_relpath_template.format(N=state.current_iteration)
        response_file = session_dir / response_rel

        # Should strictly exist if we are in PLANNED, but safety check
        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        result: ProcessingResult = profile_instance.process_planning_response(content)

        if result.status == WorkflowStatus.ERROR:
            # Recoverable error - stay in PLANNED, set last_error
            state.last_error = result.error_message or "Failed to process planning response"
            self.session_store.save(state)
            return state

        if result.status == WorkflowStatus.SUCCESS:
            # Clear any previous error on success
            state.last_error = None
            # Plan is a session-level file now
            plan_relpath = ED_APPROVAL_SPECS[WorkflowPhase.PLANNED].plan_relpath
            plan_path = session_dir / plan_relpath
            plan_path.write_text(content, encoding="utf-8")

            # Transition to GENERATING
            state.current_iteration = 1
            iteration_dir = session_dir / f"iteration-{state.current_iteration}"
            iteration_dir.mkdir(parents=True, exist_ok=True)

            state.phase = WorkflowPhase.GENERATING
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

            # Generate generation prompt immediately on entry
            gen_spec = ING_APPROVAL_SPECS[WorkflowPhase.GENERATING]
            gen_prompt_rel = gen_spec.prompt_relpath_template.format(N=state.current_iteration)
            gen_prompt_file = session_dir / gen_prompt_rel
            gen_prompt_file.parent.mkdir(parents=True, exist_ok=True)

            gen_content = profile_instance.generate_generation_prompt(self._prompt_context(state=state))
            gen_prompt_file.write_text(gen_content, encoding="utf-8")

        return state

    def _step_generating(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle GENERATING phase logic.

        Prompt was generated on entry to GENERATING.
        Check if response exists and transition to GENERATED.
        """
        session_dir = self.sessions_root / session_id

        spec = ING_APPROVAL_SPECS[WorkflowPhase.GENERATING]
        prompt_rel = spec.prompt_relpath_template.format(N=state.current_iteration)
        response_rel = spec.response_relpath_template.format(N=state.current_iteration)

        prompt_file = session_dir / prompt_rel
        response_file = session_dir / response_rel

        # Check for response and process if exists
        if response_file.exists():
            content = response_file.read_text(encoding="utf-8")
            profile_instance = ProfileFactory.create(state.profile)

            result: ProcessingResult = profile_instance.process_generation_response(
                content, session_dir, state.current_iteration
            )

            if result.status == WorkflowStatus.ERROR:
                # Recoverable error - stay in GENERATING, set last_error
                state.last_error = result.error_message or "Failed to process generation response"
                self.session_store.save(state)
                return state

            if result.status == WorkflowStatus.SUCCESS:
                # Clear any previous error on success
                state.last_error = None
                write_artifacts(session_dir=session_dir, state=state, result=result)
                state.phase = WorkflowPhase.GENERATED
                state.status = WorkflowStatus.IN_PROGRESS
                self._append_phase_history(state, phase=state.phase, status=state.status)
                self.session_store.save(state)
            return state

        # Auto-approval bypass (for profiles that auto-approve generation)
        if prompt_file.exists():
            profile_instance = ProfileFactory.create(state.profile)
            try:
                result = profile_instance.process_generation_response("", session_dir, state.current_iteration)
                if result.approved and result.status == WorkflowStatus.SUCCESS:
                    state.phase = WorkflowPhase.GENERATED
                    state.status = WorkflowStatus.IN_PROGRESS
                    self._append_phase_history(state, phase=state.phase, status=state.status)
                    self.session_store.save(state)
            except Exception:
                pass

        return state

    def _step_generated(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle GENERATED -> REVIEWING.

        - Gate on code artifacts under the resolver-derived code directory.
        - If no relevant artifacts exist, or any are unhashed, block.
        - If all relevant artifacts are hashed, transition to REVIEWING and generate review-prompt.md.
        """
        session_dir = self.sessions_root / session_id

        spec = ED_APPROVAL_SPECS[WorkflowPhase.GENERATED]
        code_dir_rel = spec.code_dir_relpath_template.format(N=state.current_iteration)

        relevant_artifacts = [
            a for a in state.artifacts
            if a.path.startswith(f"{code_dir_rel}/")
        ]

        # If there are NO relevant code artifacts, block.
        if not relevant_artifacts:
            return state

        # If any relevant code artifact is unhashed, block.
        if any(a.sha256 is None for a in relevant_artifacts):
            return state

        # All present and hashed -> Advance to REVIEWING
        state.phase = WorkflowPhase.REVIEWING
        state.status = WorkflowStatus.IN_PROGRESS
        self._append_phase_history(state, phase=state.phase, status=state.status)
        self.session_store.save(state)

        # Generate review prompt immediately on entry
        review_spec = ING_APPROVAL_SPECS[WorkflowPhase.REVIEWING]
        review_prompt_rel = review_spec.prompt_relpath_template.format(N=state.current_iteration)
        review_prompt_file = session_dir / review_prompt_rel
        review_prompt_file.parent.mkdir(parents=True, exist_ok=True)

        profile_instance = ProfileFactory.create(state.profile)
        review_content = profile_instance.generate_review_prompt(self._prompt_context(state=state))
        review_prompt_file.write_text(review_content, encoding="utf-8")

        return state

    def _step_reviewing(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVIEWING phase logic.

        Prompt was generated on entry to REVIEWING.
        Check if response exists and transition to REVIEWED.
        """
        session_dir = self.sessions_root / session_id

        spec = ING_APPROVAL_SPECS[WorkflowPhase.REVIEWING]
        response_rel = spec.response_relpath_template.format(N=state.current_iteration)
        response_file = session_dir / response_rel

        if response_file.exists():
            state.phase = WorkflowPhase.REVIEWED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        return state

    def _step_reviewed(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVIEWED outcomes based on review-response.md."""
        if not state.review_approved:
            return state

        session_dir = self.sessions_root / session_id

        spec = ED_APPROVAL_SPECS[WorkflowPhase.REVIEWED]
        response_rel = spec.response_relpath_template.format(N=state.current_iteration)
        response_file = session_dir / response_rel

        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        result: ProcessingResult = profile_instance.process_review_response(content)

        # Recoverable error - stay in REVIEWED, set last_error
        if result.status == WorkflowStatus.ERROR:
            state.last_error = result.error_message or "Failed to process review response"
            self.session_store.save(state)
            return state

        entering_revising = False

        # Clear any previous error on success
        state.last_error = None

        if result.status == WorkflowStatus.SUCCESS:
            state.phase = WorkflowPhase.COMPLETE
            state.status = WorkflowStatus.SUCCESS
        elif result.status == WorkflowStatus.FAILED:
            previous_iteration = state.current_iteration
            state.current_iteration += 1
            new_iteration_dir = session_dir / f"iteration-{state.current_iteration}"
            new_iteration_dir.mkdir(parents=True, exist_ok=True)

            # Copy code files from previous iteration to new iteration
            previous_code_dir = session_dir / f"iteration-{previous_iteration}" / "code"
            new_code_dir = new_iteration_dir / "code"
            if previous_code_dir.exists():
                def copy_if_missing(src, dst):
                    if not Path(dst).exists():
                        shutil.copy2(src, dst)

                shutil.copytree(previous_code_dir, new_code_dir,
                                dirs_exist_ok=True, copy_function=copy_if_missing)

            state.phase = WorkflowPhase.REVISING
            state.status = WorkflowStatus.IN_PROGRESS
            entering_revising = True
        elif result.status == WorkflowStatus.CANCELLED:
            state.phase = WorkflowPhase.CANCELLED
            state.status = WorkflowStatus.CANCELLED
        else:
            return state

        self._append_phase_history(state, phase=state.phase, status=state.status)
        self.session_store.save(state)

        # Generate revision prompt immediately on entry to REVISING
        if entering_revising:
            rev_spec = ING_APPROVAL_SPECS[WorkflowPhase.REVISING]
            rev_prompt_rel = rev_spec.prompt_relpath_template.format(N=state.current_iteration)
            rev_prompt_file = session_dir / rev_prompt_rel
            rev_prompt_file.parent.mkdir(parents=True, exist_ok=True)

            rev_content = profile_instance.generate_revision_prompt(self._prompt_context(state=state))
            rev_prompt_file.write_text(rev_content, encoding="utf-8")

        return state

    def _step_revising(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVISING phase logic.

        Prompt was generated on entry to REVISING.
        Check if response exists, process it, and transition to REVISED.
        """
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"

        spec = ING_APPROVAL_SPECS[WorkflowPhase.REVISING]
        response_rel = spec.response_relpath_template.format(N=state.current_iteration)
        response_file = session_dir / response_rel

        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        result: ProcessingResult = profile_instance.process_revision_response(
            content, session_dir, state.current_iteration
        )

        # Recoverable error - stay in REVISING, set last_error
        if result.status == WorkflowStatus.ERROR:
            state.last_error = result.error_message or "Failed to process revision response"
            self.session_store.save(state)
            return state

        if result.status == WorkflowStatus.SUCCESS:
            # Clear any previous error on success
            state.last_error = None
            if result.write_plan:
                write_artifacts(session_dir=session_dir, state=state, result=result)
            else:
                # Fallback: Extract and write artifacts using legacy bundle_extractor
                try:
                    profile_module = state.profile.replace("-", "_")
                    extractor_module = importlib.import_module(f"profiles.{profile_module}.bundle_extractor")
                    if hasattr(extractor_module, "extract_files"):
                        files = extractor_module.extract_files(content)
                        code_dir = iteration_dir / "code"
                        code_dir.mkdir(parents=True, exist_ok=True)
                        for filename, file_content in files.items():
                            (code_dir / filename).write_text(file_content, encoding="utf-8")
                except ImportError:
                    state.phase = WorkflowPhase.ERROR
                    state.status = WorkflowStatus.ERROR
                    self._append_phase_history(state, phase=state.phase, status=state.status)
                    self.session_store.save(state)
                    return state

            state.phase = WorkflowPhase.REVISED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        elif result.status == WorkflowStatus.CANCELLED:
            state.phase = WorkflowPhase.CANCELLED
            state.status = WorkflowStatus.CANCELLED
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        return state

    def _step_revised(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVISED -> REVIEWING.

        - Gate on code artifacts under the resolver-derived code directory.
        - If no relevant artifacts exist, or any are unhashed, block.
        - If all relevant artifacts are hashed, transition to REVIEWING and generate review-prompt.md.
        """
        session_dir = self.sessions_root / session_id

        spec = ED_APPROVAL_SPECS[WorkflowPhase.REVISED]
        code_dir_rel = spec.code_dir_relpath_template.format(N=state.current_iteration)

        relevant_artifacts = [
            a for a in state.artifacts
            if a.path.startswith(f"{code_dir_rel}/")
        ]

        # If there are NO relevant code artifacts, block.
        if not relevant_artifacts:
            return state

        # If any relevant code artifact is unhashed, block.
        if any(a.sha256 is None for a in relevant_artifacts):
            return state

        # All present and hashed -> Advance to REVIEWING
        state.phase = WorkflowPhase.REVIEWING
        state.status = WorkflowStatus.IN_PROGRESS
        self._append_phase_history(state, phase=state.phase, status=state.status)
        self.session_store.save(state)

        # Generate review prompt immediately on entry
        review_spec = ING_APPROVAL_SPECS[WorkflowPhase.REVIEWING]
        review_prompt_rel = review_spec.prompt_relpath_template.format(N=state.current_iteration)
        review_prompt_file = session_dir / review_prompt_rel
        review_prompt_file.parent.mkdir(parents=True, exist_ok=True)

        profile_instance = ProfileFactory.create(state.profile)
        review_content = profile_instance.generate_review_prompt(self._prompt_context(state=state))
        review_prompt_file.write_text(review_content, encoding="utf-8")

        return state

    @staticmethod
    def _append_phase_history(
        state: WorkflowState, *, phase: WorkflowPhase, status: WorkflowStatus
    ) -> None:
        """Append a phase-history entry using the canonical model."""
        state.phase_history.append(PhaseTransition(phase=phase, status=status))

    def _prompt_context(self, *, state: WorkflowState) -> dict[str, Any]:
        """Build context dict for template rendering.

        All metadata fields are flattened into the context so they're
        automatically available as {{KEY}} placeholders in templates.
        """
        context = {
            "session_id": state.session_id,
            "profile": state.profile,
            "scope": state.scope,
            "entity": state.entity,
            "providers": state.providers,
            "execution_mode": state.execution_mode,
            "bounded_context": state.bounded_context,
            "table": state.table,
            "dev": state.dev,
            "task_id": state.task_id,
            "iteration": getattr(state, "current_iteration", None),
            "date": date.today().isoformat(),
            "phase": state.phase,
            "status": state.status,
        }
        # Flatten metadata fields into context for template access
        if state.metadata:
            context.update(state.metadata)

        # Add code_files for REVIEWING and REVISING phases
        if state.phase in (WorkflowPhase.REVIEWING, WorkflowPhase.REVISING):
            # For REVIEWING: code is in current iteration
            # For REVISING: iteration was incremented, so code is in previous iteration
            code_iteration = (
                state.current_iteration
                if state.phase == WorkflowPhase.REVIEWING
                else state.current_iteration - 1
            )
            code_dir_prefix = f"iteration-{code_iteration}/code/"
            code_files = [
                a.path for a in state.artifacts
                if a.path.startswith(code_dir_prefix)
            ]
            context["code_files"] = code_files

        return context



def _build_initial_state(
    *,
    session_id: str,
    profile: str,
    scope: str,
    entity: str,
    providers: dict[str, str],
    execution_mode: ExecutionMode,
    bounded_context: str | None,
    table: str | None,
    dev: str | None,
    task_id: str | None,
    metadata: dict[str, Any] | None,
) -> WorkflowState:
    """Build the initial `WorkflowState` for a new session.

    Initializes the workflow in:
    - phase = WorkflowPhase.INITIALIZED
    - status = WorkflowStatus.IN_PROGRESS
    and seeds `phase_history` with the initial (phase, status) entry.

    This function does not perform any I/O and does not create directories.

    Returns:
        A fully-populated `WorkflowState` instance representing the start of a run.
    """
    initial_phase = WorkflowPhase.INITIALIZED
    initial_status = WorkflowStatus.IN_PROGRESS

    return WorkflowState(
        session_id=session_id,
        profile=profile,
        scope=scope,
        entity=entity,
        providers=providers,
        execution_mode=execution_mode,
        bounded_context=bounded_context,
        table=table,
        dev=dev,
        task_id=task_id,
        metadata=metadata or {},
        phase=initial_phase,
        status=initial_status,
        standards_hash="0" * 64,
        phase_history=[PhaseTransition(phase=initial_phase, status=initial_status)],
    )
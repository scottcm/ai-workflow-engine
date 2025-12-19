from __future__ import annotations

import importlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiwf.application.artifact_writer import write_artifacts
from aiwf.domain.constants import PLANS_DIR, PROMPTS_DIR, RESPONSES_DIR
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


@dataclass(frozen=True)
class WorkflowOrchestrator:
    """Engine-owned workflow orchestration.

    This orchestrator owns deterministic phase transitions and persistence of
    `WorkflowState`. Profiles remain responsible for generating prompts and
    processing LLM responses; the orchestrator decides what happens next.

    Current implementation covers M5 Slice A–E:
    - initialize_run(): create and persist the initial WorkflowState (INITIALIZED)
    - step(): advance by exactly one unit of work for:
      - INITIALIZED -> PLANNING
      - PLANNING -> PLANNED when a planning response exists and processing succeeds
      - PLANNED -> GENERATING when generation begins (creates iteration-1/)
      - GENERATING -> GENERATED when a generation response exists and processing succeeds
      - GENERATED -> REVIEWING
      - REVIEWING -> COMPLETE / REVISING / ERROR / CANCELLED based on review outcome
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

        self.session_store.save(state)
        return session_id

    def step(self, session_id: str) -> WorkflowState:
        """Advance the workflow by one deterministic unit of work.

        Loads the persisted `WorkflowState` for `session_id` and performs at most
        one phase transition per call. If required input artifacts are missing,
        the workflow is considered blocked and this method returns the current
        state unchanged without persisting.

        Implemented transitions:
        - INITIALIZED -> PLANNING
        - PLANNING:
            - Generates planning-prompt.md if missing.
            - Transitions to PLANNED if planning-response.md exists.
        - PLANNED:
            - Processes planning-response.md.
            - If success: Writes plan.md, creates iteration-1/, sets current_iteration=1 -> GENERATING.
        - GENERATING:
            - Generates generation-prompt.md if missing.
            - Transitions to GENERATED if generation-response.md exists.
        - GENERATED:
            - Processes generation-response.md.
            - If success: Transitions to REVIEWING.
        - REVIEWING:
            - Generates review-prompt.md if missing.
            - Transitions to REVIEWED if review-response.md exists.
        - REVIEWED:
            - Processes review-response.md.
            - SUCCESS   -> COMPLETE (status=SUCCESS)
            - FAILED    -> REVISING (status=IN_PROGRESS; increments iteration; creates new iteration dir)
            - ERROR     -> ERROR (status=ERROR)
            - CANCELLED -> CANCELLED (status=CANCELLED)
        - REVISING:
            - Generates revision-prompt.md if missing.
            - Transitions to REVISED if revision-response.md exists.
        - REVISED:
            - Processes revision-response.md.
            - If success: transitions to REVIEWING.
            - ERROR     -> ERROR
            - CANCELLED -> CANCELLED

        Args:
            session_id: Identifier of the workflow session to advance.

        Returns:
            The current workflow state after applying at most one unit of work.
        """
        state = self.session_store.load(session_id)

        if state.phase == WorkflowPhase.INITIALIZED:
            return self._step_initialized(state)

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

    def _step_initialized(self, state: WorkflowState) -> WorkflowState:
        """Handle INITIALIZED -> PLANNING."""
        state.phase = WorkflowPhase.PLANNING
        state.status = WorkflowStatus.IN_PROGRESS
        self._append_phase_history(state, phase=state.phase, status=state.status)
        self.session_store.save(state)
        return state

    def _step_planning(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle PLANNING phase logic.

        - If planning-response.md exists: transition to PLANNED (no processing).
        - If planning-prompt.md missing: generate and write it.
        """
        session_dir = self.sessions_root / session_id
        prompts_dir = session_dir / PROMPTS_DIR
        responses_dir = session_dir / RESPONSES_DIR
        prompt_file = prompts_dir / "planning-prompt.md"
        response_file = responses_dir / "planning-response.md"

        # 1. Check for response
        if response_file.exists():
            state.phase = WorkflowPhase.PLANNED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)
            return state

        # 2. Generate prompt if missing
        if not prompt_file.exists():
            profile_instance = ProfileFactory.create(state.profile)
            # Assuming profile has generate_planning_prompt - implicitly required by flow
            content = profile_instance.generate_planning_prompt(self._prompt_context(state=state))
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(content, encoding="utf-8")
            # Stay in PLANNING waiting for response
            return state

        return state

    def _step_planned(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle PLANNED -> GENERATING.

        - Process planning-response.md.
        - If successful, write plan.md and create iteration-1/.
        """
        session_dir = self.sessions_root / session_id
        response_file = session_dir / RESPONSES_DIR / "planning-response.md"

        # Should strictly exist if we are in PLANNED, but safety check
        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        result: ProcessingResult = profile_instance.process_planning_response(content)

        if result.status == WorkflowStatus.SUCCESS:
            plans_dir = session_dir / PLANS_DIR
            plans_dir.mkdir(parents=True, exist_ok=True)
            (plans_dir / "plan.md").write_text(content, encoding="utf-8")

            # Transition to GENERATING
            state.current_iteration = 1
            iteration_dir = session_dir / f"iteration-{state.current_iteration}"
            iteration_dir.mkdir(parents=True, exist_ok=True)

            state.phase = WorkflowPhase.GENERATING
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        return state

    def _step_generating(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle GENERATING phase logic.

        - If generation-response.md exists: transition to GENERATED (no processing).
        - If generation-prompt.md missing: generate and write it.
        """
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        prompts_dir = iteration_dir / PROMPTS_DIR
        responses_dir = iteration_dir / RESPONSES_DIR
        prompt_file = prompts_dir / "generation-prompt.md"
        response_file = responses_dir / "generation-response.md"

        # 1. Check for response
        if response_file.exists():
            state.phase = WorkflowPhase.GENERATED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)
            return state

        # 2. Generate prompt if missing
        if not prompt_file.exists():
            profile_instance = ProfileFactory.create(state.profile)
            # Assuming profile has generate_generation_prompt
            content = profile_instance.generate_generation_prompt(self._prompt_context(state=state))
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(content, encoding="utf-8")
            return state

        return state

    def _step_generated(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle GENERATED -> REVIEWING.

        - Process generation-response.md.
        - If successful, transition to REVIEWING.
        """
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_file = iteration_dir / RESPONSES_DIR / "generation-response.md"

        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        
        result: ProcessingResult = profile_instance.process_generation_response(
            content, session_dir, state.current_iteration
        )

        if result.status == WorkflowStatus.SUCCESS:
            write_artifacts(session_dir=session_dir, state=state, result=result)

            state.phase = WorkflowPhase.REVIEWING
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        return state

    def _step_reviewing(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVIEWING phase logic.

        - If review-response.md exists: transition to REVIEWED (no processing).
        - If review-prompt.md missing: generate and write it.
        """
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        prompts_dir = iteration_dir / PROMPTS_DIR
        responses_dir = iteration_dir / RESPONSES_DIR
        prompt_file = prompts_dir / "review-prompt.md"
        response_file = responses_dir / "review-response.md"

        # 1. Check for response
        if response_file.exists():
            state.phase = WorkflowPhase.REVIEWED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)
            return state

        # 2. Generate prompt if missing
        if not prompt_file.exists():
            profile_instance = ProfileFactory.create(state.profile)
            # Assuming profile has generate_review_prompt
            content = profile_instance.generate_review_prompt(self._prompt_context(state=state))
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(content, encoding="utf-8")
            return state

        return state

    def _step_reviewed(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVIEWED outcomes based on review-response.md."""
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_file = iteration_dir / RESPONSES_DIR / "review-response.md"

        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        result: ProcessingResult = profile_instance.process_review_response(content)

        if result.status == WorkflowStatus.SUCCESS:
            state.phase = WorkflowPhase.COMPLETE
            state.status = WorkflowStatus.SUCCESS
        elif result.status == WorkflowStatus.FAILED:
            state.current_iteration += 1
            new_iteration_dir = session_dir / f"iteration-{state.current_iteration}"
            new_iteration_dir.mkdir(parents=True, exist_ok=True)
            state.phase = WorkflowPhase.REVISING
            state.status = WorkflowStatus.IN_PROGRESS
        elif result.status == WorkflowStatus.ERROR:
            state.phase = WorkflowPhase.ERROR
            state.status = WorkflowStatus.ERROR
        elif result.status == WorkflowStatus.CANCELLED:
            state.phase = WorkflowPhase.CANCELLED
            state.status = WorkflowStatus.CANCELLED
        else:
            return state

        self._append_phase_history(state, phase=state.phase, status=state.status)
        self.session_store.save(state)
        return state

    def _step_revising(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVISING phase logic.

        - If revision-response.md exists: transition to REVISED (no processing).
        - If revision-prompt.md missing: generate and write it.
        """
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        prompts_dir = iteration_dir / PROMPTS_DIR
        responses_dir = iteration_dir / RESPONSES_DIR
        prompt_file = prompts_dir / "revision-prompt.md"
        response_file = responses_dir / "revision-response.md"

        # 1. Check for response
        if response_file.exists():
            state.phase = WorkflowPhase.REVISED
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)
            return state

        # 2. Generate prompt if missing
        if not prompt_file.exists():
            profile_instance = ProfileFactory.create(state.profile)
            content = profile_instance.generate_revision_prompt(self._prompt_context(state=state))
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(content, encoding="utf-8")
            return state

        return state

    def _step_revised(self, *, session_id: str, state: WorkflowState) -> WorkflowState:
        """Handle REVISED outcome.

        - Process revision-response.md.
        - If success: extract files and transition to REVIEWING.
        - If error/cancelled: transition to ERROR/CANCELLED.
        """
        session_dir = self.sessions_root / session_id
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_file = iteration_dir / RESPONSES_DIR / "revision-response.md"

        if not response_file.exists():
            return state

        content = response_file.read_text(encoding="utf-8")
        profile_instance = ProfileFactory.create(state.profile)
        result: ProcessingResult = profile_instance.process_revision_response(
            content, session_dir, state.current_iteration
        )

        if result.status == WorkflowStatus.SUCCESS:
            # Extract and write artifacts
            try:
                extractor_module = importlib.import_module(f"profiles.{state.profile}.bundle_extractor")
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

            state.phase = WorkflowPhase.REVIEWING
            state.status = WorkflowStatus.IN_PROGRESS
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)
        elif result.status == WorkflowStatus.ERROR:
            state.phase = WorkflowPhase.ERROR
            state.status = WorkflowStatus.ERROR
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)
        elif result.status == WorkflowStatus.CANCELLED:
            state.phase = WorkflowPhase.CANCELLED
            state.status = WorkflowStatus.CANCELLED
            self._append_phase_history(state, phase=state.phase, status=state.status)
            self.session_store.save(state)

        return state

    @staticmethod
    def _append_phase_history(
        state: WorkflowState, *, phase: WorkflowPhase, status: WorkflowStatus
    ) -> None:
        """Append a phase-history entry using the canonical model."""
        state.phase_history.append(PhaseTransition(phase=phase, status=status))

    def _prompt_context(self, *, state: WorkflowState) -> dict[str, Any]:
        return {
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
            "metadata": state.metadata,
            "current_iteration": getattr(state, "current_iteration", None),
            "phase": state.phase,
            "status": state.status,
        }



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
        phase_history=[PhaseTransition(phase=initial_phase, status=initial_status)],
    )

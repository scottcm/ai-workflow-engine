"""Artifact service for pre-transition approval handling.

Phase 5 of orchestrator modularization: centralize hashing and artifact creation.
Owns the _APPROVAL_HANDLERS dispatch table and all _approve_* methods.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Any, Callable

from aiwf.domain.models.workflow_state import (
    Artifact,
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
)
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.validation.path_validator import PathValidator


# Dispatch table: (phase, stage) -> handler method name
# Adding a new approval handler requires only:
# 1. Add entry here
# 2. Implement the _approve_* method
_APPROVAL_HANDLERS: dict[tuple[WorkflowPhase, WorkflowStage | None], str] = {
    (WorkflowPhase.PLAN, WorkflowStage.RESPONSE): "_approve_plan_response",
    (WorkflowPhase.GENERATE, WorkflowStage.RESPONSE): "_approve_generate_response",
    (WorkflowPhase.REVIEW, WorkflowStage.RESPONSE): "_approve_review_response",
    (WorkflowPhase.REVISE, WorkflowStage.RESPONSE): "_approve_revise_response",
}


class ArtifactService:
    """Service for pre-transition approval handling.

    Centralizes hashing and artifact creation that happens when content
    is approved, BEFORE the state transition to the next phase.

    Uses double dispatch pattern - looks up handler by (phase, stage) tuple.
    """

    def handle_pre_transition_approval(
        self,
        state: WorkflowState,
        session_dir: Path,
        add_message: Callable[[WorkflowState, str], None],
    ) -> None:
        """Handle approval logic BEFORE state transition.

        Uses double dispatch - looks up handler by (phase, stage) tuple.
        No if...elif chains; adding handlers only touches the dispatch table.

        Args:
            state: Current workflow state (modified in place)
            session_dir: Session directory path
            add_message: Callback to add progress messages
        """
        key = (state.phase, state.stage)
        handler_name = _APPROVAL_HANDLERS.get(key)

        if handler_name is not None:
            handler = getattr(self, handler_name)
            handler(state, session_dir, add_message)

    def copy_plan_to_session(
        self,
        state: WorkflowState,
        session_dir: Path,
        add_message: Callable[[WorkflowState, str], None],
    ) -> None:
        """Copy planning-response.md to plan.md at session level.

        Called when entering GENERATE phase after plan is approved.

        Args:
            state: Current workflow state
            session_dir: Session directory path
            add_message: Callback to add progress messages
        """
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        source = iteration_dir / "planning-response.md"
        dest = session_dir / "plan.md"

        if not source.exists():
            raise ValueError(f"Cannot copy plan: {source} not found")

        shutil.copy2(source, dest)
        add_message(state, "Copied plan to session")

    def _approve_plan_response(
        self,
        state: WorkflowState,
        session_dir: Path,
        add_message: Callable[[WorkflowState, str], None],
    ) -> None:
        """Approve plan response: hash planning-response.md, set plan_approved."""
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "planning-response.md"

        if response_path.exists():
            content = response_path.read_bytes()
            state.plan_hash = hashlib.sha256(content).hexdigest()
            state.plan_approved = True
            add_message(state, "Plan approved")
        else:
            raise ValueError(
                f"Cannot approve: planning-response.md not found at {response_path}"
            )

    def _approve_generate_response(
        self,
        state: WorkflowState,
        session_dir: Path,
        add_message: Callable[[WorkflowState, str], None],
    ) -> None:
        """Approve generation response: extract code, create artifacts."""
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "generation-response.md"

        if not response_path.exists():
            raise ValueError(
                f"Cannot approve: generation-response.md not found at {response_path}"
            )

        content = response_path.read_text(encoding="utf-8")

        # Use profile to process and extract code
        profile = ProfileFactory.create(state.profile)
        result = profile.process_generation_response(
            content, session_dir, state.current_iteration
        )

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

            add_message(state, f"Extracted {len(result.write_plan.writes)} code file(s)")
        else:
            add_message(state, "Generation approved (no code extracted)")

    def _approve_review_response(
        self,
        state: WorkflowState,
        session_dir: Path,
        add_message: Callable[[WorkflowState, str], None],
    ) -> None:
        """Approve review response: hash review-response.md, set review_approved."""
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "review-response.md"

        if response_path.exists():
            content = response_path.read_bytes()
            state.review_hash = hashlib.sha256(content).hexdigest()
            state.review_approved = True
            add_message(state, "Review approved")
        else:
            raise ValueError(
                f"Cannot approve: review-response.md not found at {response_path}"
            )

    def _approve_revise_response(
        self,
        state: WorkflowState,
        session_dir: Path,
        add_message: Callable[[WorkflowState, str], None],
    ) -> None:
        """Approve revision response: extract code, update artifacts."""
        iteration_dir = session_dir / f"iteration-{state.current_iteration}"
        response_path = iteration_dir / "revision-response.md"

        if not response_path.exists():
            raise ValueError(
                f"Cannot approve: revision-response.md not found at {response_path}"
            )

        content = response_path.read_text(encoding="utf-8")

        # Use profile to process and extract revised code
        profile = ProfileFactory.create(state.profile)
        result = profile.process_revision_response(
            content, session_dir, state.current_iteration
        )

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

            add_message(
                state, f"Extracted {len(result.write_plan.writes)} revised code file(s)"
            )
        else:
            add_message(state, "Revision approved (no code extracted)")
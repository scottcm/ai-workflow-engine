"""ApprovalGateService - handles approval gate execution and result handling.

Phase 2 of orchestrator modularization: extracts approval gating logic
into a focused service while maintaining backward test compatibility.

The service provides the core gating logic. Orchestrator methods delegate
to this service but remain available for existing test compatibility.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from aiwf.application.approval_config import ApprovalConfig
from aiwf.application.storage import SessionFileGateway
from aiwf.application.transitions import TransitionTable
from aiwf.domain.errors import ProviderError
from aiwf.domain.models.approval_result import (
    ApprovalDecision,
    ApprovalResult,
    validate_approval_result,
)
from aiwf.domain.models.workflow_state import (
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.profiles.profile_factory import ProfileFactory

if TYPE_CHECKING:
    from aiwf.application.workflow_orchestrator import WorkflowOrchestrator


class _RegenerationNotImplemented(Exception):
    """Internal: profile declared capability but didn't implement."""

    pass


@dataclass
class GateContext:
    """Context for approval gate operations.

    Bundles orchestrator helpers needed by the gate service.
    Allows the service to be tested in isolation with mock context.

    Gate methods are callbacks to orchestrator so existing test patches work.
    """

    # Approval configuration
    approval_config: ApprovalConfig

    # Callbacks to orchestrator methods (essential - orchestrator owns these)
    add_message: Callable[[WorkflowState, str], None]
    build_base_context: Callable[[WorkflowState], dict[str, Any]]
    build_provider_context: Callable[[WorkflowState], dict[str, Any]]
    get_approver: Callable[[WorkflowPhase, WorkflowStage], Any]
    save_state: Callable[[WorkflowState], None]
    action_retry: Callable[[WorkflowState, Path], None]
    execute_action: Callable[[WorkflowState, Any, str], None]
    handle_pre_transition_approval: Callable[[WorkflowState, Path], None]
    write_regenerated_prompt: Callable[[WorkflowState, Path, Any], None]


class ApprovalGateService:
    """Service for running approval gates and handling results.

    Coordinates approval evaluation, rejection handling, retry logic,
    and auto-continue flow.
    """

    def build_approval_files(
        self,
        state: WorkflowState,
        session_dir: Path,
        context: GateContext,
    ) -> dict[str, str | None]:
        """Build files dict for approval evaluation.

        Returns dict of filepath -> content for files relevant to approval.
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
            (WorkflowPhase.REVISE, WorkflowStage.RESPONSE): [
                "revision-response.md",
                "revision-issues.md",
            ],
        }

        file_names = phase_files.get((state.phase, state.stage), [])

        for name in file_names:
            file_path = iteration_dir / name
            if file_path.exists():
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

    def build_approval_context(
        self,
        state: WorkflowState,
        session_dir: Path,
        context: GateContext,
    ) -> dict[str, Any]:
        """Build context dict for approval providers."""
        ctx = context.build_base_context(state)
        stage_config = context.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )
        ctx.update(
            {
                "allow_rewrite": stage_config.allow_rewrite,
                "session_dir": str(session_dir),
                "plan_file": str(session_dir / "plan.md"),
            }
        )
        return ctx

    def run_approval_gate(
        self,
        state: WorkflowState,
        session_dir: Path,
        context: GateContext,
    ) -> ApprovalResult:
        """Run approval gate for current phase/stage.

        Returns:
            ApprovalResult (never None - PENDING replaces None for manual approval)
        """
        if state.stage is None:
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        approver = context.get_approver(state.phase, state.stage)
        files = self.build_approval_files(state, session_dir, context)
        approval_ctx = self.build_approval_context(state, session_dir, context)

        result = approver.evaluate(
            phase=state.phase,
            stage=state.stage,
            files=files,
            context=approval_ctx,
        )

        return result

    def run_after_action(
        self,
        state: WorkflowState,
        session_dir: Path,
        context: GateContext,
    ) -> None:
        """Run approval gate after content creation and handle result.

        Called automatically after CREATE_PROMPT and CALL_AI actions.
        Service owns gate logic; uses context for orchestrator dependencies.
        """
        if state.stage is None:
            return  # No gate for stageless states

        try:
            result = self.run_approval_gate(state, session_dir, context)
            result = validate_approval_result(result)
        except (ProviderError, TimeoutError, TypeError) as e:
            state.last_error = f"Approval gate error: {e}"
            context.add_message(state, f"Approval failed: {e}. Run 'approve' to retry.")
            context.save_state(state)
            return

        if result.decision == ApprovalDecision.PENDING:
            state.pending_approval = True
            if result.feedback:
                context.add_message(state, result.feedback)
            context.save_state(state)
            return

        if result.decision == ApprovalDecision.REJECTED:
            rejection_result = self.handle_approval_rejection(state, session_dir, result, context)
            if rejection_result is not None:
                return  # Workflow paused for user intervention
            # Retry succeeded - fall through to auto-continue

        # APPROVED (or retry succeeded) - auto-continue
        self._clear_approval_state(state)
        context.handle_pre_transition_approval(state, session_dir)
        self._auto_continue(state, session_dir, context)

    def handle_approval_rejection(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
        context: GateContext,
    ) -> WorkflowState | None:
        """Handle approval rejection by dispatching to stage-specific handler.

        Returns None if retry succeeded (caller should proceed with transition).
        Returns state if workflow should pause.
        """
        state.approval_feedback = result.feedback
        state.retry_count += 1

        if state.stage == WorkflowStage.PROMPT:
            return self.handle_prompt_rejection(state, session_dir, result, context)
        else:
            return self.handle_response_rejection(state, session_dir, result, context)

    def handle_prompt_rejection(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
        context: GateContext,
    ) -> WorkflowState | None:
        """Handle rejection during PROMPT stage.

        Attempts suggested_content application or profile regeneration.
        Falls back to pausing for user review/edit.
        """
        stage_config = context.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )

        # Try suggested_content if available and allowed
        if result.suggested_content and stage_config.allow_rewrite:
            self._apply_suggested_content_to_prompt(
                state, session_dir, result.suggested_content, context
            )
            state.pending_approval = True
            context.add_message(state, "Suggested content applied to prompt file")
            context.save_state(state)
            return state

        # Try profile regeneration if supported
        profile = ProfileFactory.create(state.profile)
        if profile.get_metadata().get("can_regenerate_prompts", False):
            try:
                regeneration_result = self._try_prompt_regeneration(
                    state, session_dir, result, context
                )
                return regeneration_result
            except _RegenerationNotImplemented:
                pass  # Fall through to user pause

        # Pause for user to review/edit and re-approve
        state.pending_approval = True
        context.add_message(state, f"Prompt rejected: {result.feedback or 'no feedback'}")
        context.save_state(state)
        return state

    def handle_response_rejection(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
        context: GateContext,
    ) -> WorkflowState | None:
        """Handle rejection during RESPONSE stage with retry loop.

        Auto-retries up to max_retries using AI regeneration.
        Returns None if retry succeeded, state if paused.
        """
        stage_config = context.approval_config.get_stage_config(
            state.phase.value, state.stage.value if state.stage else "prompt"
        )

        # Store suggested_content if available
        if result.suggested_content and stage_config.allow_rewrite:
            state.suggested_content = result.suggested_content
            context.add_message(state, "Suggested content available (not auto-applied yet)")

        # Retry loop - only for stages with max_retries > 0
        while state.retry_count <= stage_config.max_retries and stage_config.max_retries > 0:
            context.add_message(
                state,
                f"Retry {state.retry_count}/{stage_config.max_retries}: regenerating with feedback",
            )

            context.action_retry(state, session_dir)
            new_result = self.run_approval_gate(state, session_dir, context)

            if new_result.decision == ApprovalDecision.PENDING:
                state.pending_approval = True
                context.save_state(state)
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
            context.add_message(
                state,
                "Approval failed: max retries exceeded. Review feedback and retry or cancel.",
            )

        # Pause workflow for human intervention
        state.pending_approval = True
        context.save_state(state)
        return state

    def _try_prompt_regeneration(
        self,
        state: WorkflowState,
        session_dir: Path,
        result: ApprovalResult,
        context: GateContext,
    ) -> WorkflowState | None:
        """Attempt to regenerate prompt using profile capability."""
        profile = ProfileFactory.create(state.profile)
        try:
            provider_ctx = context.build_provider_context(state)
            new_prompt = profile.regenerate_prompt(
                state.phase,
                result.feedback or "",
                provider_ctx,
            )

            context.write_regenerated_prompt(state, session_dir, new_prompt)
            context.add_message(state, "Prompt regenerated based on feedback")

            new_result = self.run_approval_gate(state, session_dir, context)

            if new_result.decision == ApprovalDecision.PENDING:
                state.pending_approval = True
                context.save_state(state)
                return state

            if new_result.decision == ApprovalDecision.APPROVED:
                return None  # Proceed with transition

            # Still rejected - recurse
            return self.handle_approval_rejection(state, session_dir, new_result, context)

        except NotImplementedError:
            raise _RegenerationNotImplemented()

    def _apply_suggested_content_to_prompt(
        self,
        state: WorkflowState,
        session_dir: Path,
        suggested_content: str,
        context: GateContext,
    ) -> None:
        """Apply suggested content to the prompt file."""
        if state.phase not in SessionFileGateway.PHASE_FILES:
            return

        gateway = SessionFileGateway(session_dir)
        if gateway.prompt_exists(state.current_iteration, state.phase):
            gateway.write_prompt(state.current_iteration, state.phase, suggested_content)

    def _clear_approval_state(self, state: WorkflowState) -> None:
        """Clear approval tracking fields after successful approval."""
        state.approval_feedback = None
        state.suggested_content = None
        state.retry_count = 0

    def _auto_continue(
        self,
        state: WorkflowState,
        session_dir: Path,
        context: GateContext,
    ) -> None:
        """Automatically continue to next stage after approval."""
        from aiwf.application.transitions import Action

        transition = TransitionTable.get_transition(state.phase, state.stage, "approve")
        if transition is None:
            return

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
        context.execute_action(state, transition.action, state.session_id)

        # Save state
        context.save_state(state)
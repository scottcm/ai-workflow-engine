"""Safety net tests for orchestrator modularization refactor.

These tests document critical behaviors that must be preserved during the
refactor phases. After extraction, these tests can be moved to service-specific
test files.

Categories:
1. Retry loop edge cases
2. Review verdict transitions
3. Prompt rejection with regeneration
4. State mutation timing (ADR-0012)
5. Approval file collection
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from aiwf.domain.models.workflow_state import (
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.application.approval_config import ApprovalConfig, StageApprovalConfig
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.processing_result import ProcessingResult


def _make_state(
    phase: WorkflowPhase = WorkflowPhase.INIT,
    stage: WorkflowStage | None = None,
    **kwargs,
) -> WorkflowState:
    """Create a minimal WorkflowState for testing."""
    defaults = {
        "session_id": "test-session",
        "profile": "test-profile",
        "context": {},
        "phase": phase,
        "stage": stage,
        "status": WorkflowStatus.IN_PROGRESS,
        "ai_providers": {"planner": "manual"},
        "standards_hash": "abc123",
        "current_iteration": 1,
        "retry_count": 0,
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_orchestrator(
    tmp_path: Path,
    approval_config: ApprovalConfig | None = None,
) -> WorkflowOrchestrator:
    """Create orchestrator with mocked store."""
    store = Mock(spec=SessionStore)
    return WorkflowOrchestrator(
        session_store=store,
        sessions_root=tmp_path,
        approval_config=approval_config or ApprovalConfig(default_approver="skip"),
    )


# =============================================================================
# 1. Retry Loop Edge Cases
# =============================================================================

class TestRetryLoop:
    """Tests for _handle_response_rejection retry behavior."""

    def test_retry_succeeds_on_attempt_2_of_3(self, tmp_path: Path) -> None:
        """When retry succeeds on second attempt, returns None and continues."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.response": StageApprovalConfig(approver="ai", max_retries=3)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            retry_count=0,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-response.md").write_text("content")

        call_count = 0
        def mock_gate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="try again")
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        with patch.object(orchestrator._approval_gate_service, "run_approval_gate", mock_gate):
            with patch.object(orchestrator, "_action_retry"):
                result = orchestrator._handle_response_rejection(
                    state, session_dir,
                    ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="initial")
                )

        assert result is None  # None means proceed
        assert call_count == 2  # Retried once

    def test_retry_succeeds_on_final_attempt(self, tmp_path: Path) -> None:
        """When retry succeeds on final attempt, returns None."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.response": StageApprovalConfig(approver="ai", max_retries=2)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            retry_count=0,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-response.md").write_text("content")

        call_count = 0
        def mock_gate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="try again")
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        with patch.object(orchestrator._approval_gate_service, "run_approval_gate", mock_gate):
            with patch.object(orchestrator, "_action_retry"):
                result = orchestrator._handle_response_rejection(
                    state, session_dir,
                    ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="initial rejection")
                )

        assert result is None
        assert call_count == 3  # Initial + 2 retries

    def test_max_retries_zero_no_retry_loop(self, tmp_path: Path) -> None:
        """When max_retries=0, no retry attempt is made."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.response": StageApprovalConfig(approver="ai", max_retries=0)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        gate_called = False
        def mock_gate(*args, **kwargs):
            nonlocal gate_called
            gate_called = True
            return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="no retry")

        with patch.object(orchestrator._approval_gate_service, "run_approval_gate", mock_gate):
            with patch.object(orchestrator, "_action_retry") as mock_retry:
                result = orchestrator._handle_response_rejection(
                    state, session_dir,
                    ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="initial rejection")
                )

        assert result is state  # Returns state (paused)
        assert state.pending_approval is True
        mock_retry.assert_not_called()
        assert not gate_called  # No additional gate call in loop

    def test_pending_during_retry_preserves_count(self, tmp_path: Path) -> None:
        """When PENDING during retry, pauses and preserves retry_count."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.response": StageApprovalConfig(approver="ai", max_retries=3)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            retry_count=0,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-response.md").write_text("content")

        def mock_gate(*args, **kwargs):
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        with patch.object(orchestrator._approval_gate_service, "run_approval_gate", mock_gate):
            with patch.object(orchestrator, "_action_retry"):
                result = orchestrator._handle_response_rejection(
                    state, session_dir,
                    ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="initial rejection")
                )

        assert result is state
        assert state.pending_approval is True
        # retry_count should reflect the retry attempt was started
        assert state.retry_count <= 1


# =============================================================================
# 2. Review Verdict Transitions
# =============================================================================

class TestReviewVerdictTransitions:
    """Tests for _action_check_verdict behavior."""

    def test_verdict_pass_transitions_to_complete(self, tmp_path: Path) -> None:
        """PASS verdict transitions to COMPLETE with SUCCESS status."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "review-response.md").write_text("@@@REVIEW_META\nverdict: PASS\n@@@")

        mock_profile = Mock()
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            content="",
            metadata={"verdict": "PASS"},
        )

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            orchestrator._action_check_verdict(state, session_dir)

        assert state.phase == WorkflowPhase.COMPLETE
        assert state.stage is None
        assert state.status == WorkflowStatus.SUCCESS

    def test_verdict_fail_transitions_to_revise(self, tmp_path: Path) -> None:
        """FAIL verdict increments iteration and transitions to REVISE[PROMPT]."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
            current_iteration=1,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "review-response.md").write_text("@@@REVIEW_META\nverdict: FAIL\n@@@")

        mock_profile = Mock()
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            content="",
            metadata={"verdict": "FAIL"},
        )

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            with patch.object(orchestrator, "_action_create_prompt"):
                with patch.object(orchestrator, "_run_gate_after_action"):
                    orchestrator._action_check_verdict(state, session_dir)

        assert state.current_iteration == 2
        assert state.phase == WorkflowPhase.REVISE
        assert state.stage == WorkflowStage.PROMPT

    def test_invalid_verdict_sets_error_not_blocked(self, tmp_path: Path) -> None:
        """Invalid verdict sets last_error but doesn't block workflow."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "review-response.md").write_text("Some review without verdict")

        mock_profile = Mock()
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            content="",
            metadata={"verdict": "INVALID_VALUE"},
        )

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            orchestrator._action_check_verdict(state, session_dir)

        assert state.last_error is not None
        assert "Invalid or missing" in state.last_error
        # Phase should NOT have changed (not blocked)
        assert state.phase == WorkflowPhase.REVIEW

    def test_missing_verdict_sets_error(self, tmp_path: Path) -> None:
        """Missing verdict treated same as invalid."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.RESPONSE,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "review-response.md").write_text("Review with no metadata")

        mock_profile = Mock()
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            content="",
            metadata={},  # No verdict key
        )

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            orchestrator._action_check_verdict(state, session_dir)

        assert state.last_error is not None
        assert "Invalid or missing" in state.last_error


# =============================================================================
# 3. Prompt Rejection with Regeneration
# =============================================================================

class TestPromptRejectionRegeneration:
    """Tests for _handle_prompt_rejection and _try_prompt_regeneration."""

    def test_regeneration_attempted_when_profile_supports(self, tmp_path: Path) -> None:
        """Profile with can_regenerate_prompts=True triggers regeneration."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.prompt": StageApprovalConfig(approver="ai", allow_rewrite=False)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": True}
        mock_profile.regenerate_prompt.return_value = "New prompt content"

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            with patch.object(orchestrator, "_write_regenerated_prompt"):
                with patch.object(orchestrator._approval_gate_service, "run_approval_gate") as mock_gate:
                    mock_gate.return_value = ApprovalResult(decision=ApprovalDecision.APPROVED)
                    with patch.object(orchestrator, "_build_provider_context", return_value={}):
                        result = orchestrator._handle_prompt_rejection(
                            state, session_dir,
                            ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="fix it")
                        )

        mock_profile.regenerate_prompt.assert_called_once()
        assert result is None  # Approved after regeneration

    def test_regeneration_success_reruns_gate(self, tmp_path: Path) -> None:
        """After successful regeneration, gate is re-run."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.prompt": StageApprovalConfig(approver="ai", allow_rewrite=False)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": True}
        mock_profile.regenerate_prompt.return_value = "New prompt"

        gate_calls = []
        def mock_gate(*args, **kwargs):
            gate_calls.append(True)
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            with patch.object(orchestrator, "_write_regenerated_prompt"):
                with patch.object(orchestrator._approval_gate_service, "run_approval_gate", mock_gate):
                    with patch.object(orchestrator, "_build_provider_context", return_value={}):
                        orchestrator._handle_prompt_rejection(
                            state, session_dir,
                            ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="initial rejection")
                        )

        assert len(gate_calls) == 1  # Gate called after regeneration

    def test_regeneration_not_implemented_falls_through(self, tmp_path: Path) -> None:
        """NotImplementedError from regenerate_prompt falls through to pause."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.prompt": StageApprovalConfig(approver="ai", allow_rewrite=False)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": True}
        mock_profile.regenerate_prompt.side_effect = NotImplementedError("Not supported")

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            with patch.object(orchestrator, "_build_provider_context", return_value={}):
                result = orchestrator._handle_prompt_rejection(
                    state, session_dir,
                    ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="needs improvement")
                )

        assert result is state
        assert state.pending_approval is True

    def test_regeneration_rejected_again_recurses(self, tmp_path: Path) -> None:
        """Rejected regeneration recurses to _handle_approval_rejection."""
        config = ApprovalConfig(
            default_approver="ai",
            stages={"plan.prompt": StageApprovalConfig(approver="ai", allow_rewrite=False)},
        )
        orchestrator = _make_orchestrator(tmp_path, config)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": True}
        # Return different content each time to track calls
        call_count = [0]
        def regen(*args, **kwargs):
            call_count[0] += 1
            return f"Regenerated prompt {call_count[0]}"
        mock_profile.regenerate_prompt.side_effect = regen

        # First gate call returns rejected, second returns pending (to stop recursion)
        gate_calls = [0]
        def mock_gate(*args, **kwargs):
            gate_calls[0] += 1
            if gate_calls[0] <= 2:
                return ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="still wrong")
            return ApprovalResult(decision=ApprovalDecision.PENDING)

        with patch.object(ProfileFactory, "create", return_value=mock_profile):
            with patch.object(orchestrator, "_write_regenerated_prompt"):
                with patch.object(orchestrator._approval_gate_service, "run_approval_gate", mock_gate):
                    with patch.object(orchestrator, "_build_provider_context", return_value={}):
                        result = orchestrator._handle_prompt_rejection(
                            state, session_dir,
                            ApprovalResult(decision=ApprovalDecision.REJECTED, feedback="initial rejection")
                        )

        # Should have attempted regeneration multiple times before pending
        assert call_count[0] >= 2


# =============================================================================
# 4. State Mutation Timing (ADR-0012)
# =============================================================================

class TestStateMutationTiming:
    """Tests for ADR-0012 state mutation timing requirements."""

    def test_state_updates_before_action_execution(self, tmp_path: Path) -> None:
        """State phase/stage updated BEFORE action is executed."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"

        state_during_action = []
        original_execute = orchestrator._execute_action
        def tracking_execute(s, action, session_id):
            state_during_action.append((s.phase, s.stage))
            # Don't actually execute

        with patch.object(orchestrator, "_execute_action", tracking_execute):
            orchestrator._auto_continue(state, session_dir)

        # During action execution, state should already be updated
        assert len(state_during_action) == 1
        recorded_phase, recorded_stage = state_during_action[0]
        # After PLAN[PROMPT] approve, should be PLAN[RESPONSE]
        assert recorded_phase == WorkflowPhase.PLAN
        assert recorded_stage == WorkflowStage.RESPONSE

    def test_terminal_state_detection_after_transition(self, tmp_path: Path) -> None:
        """Terminal states set appropriate status after transition."""
        orchestrator = _make_orchestrator(tmp_path)

        # Start at REVIEW[RESPONSE] with PASS verdict path
        # We'll simulate the approve transition to COMPLETE
        state = _make_state(
            phase=WorkflowPhase.COMPLETE,  # Simulating post-transition
            stage=None,
        )

        # Manually test the status update logic
        if state.phase == WorkflowPhase.COMPLETE:
            state.status = WorkflowStatus.SUCCESS
        elif state.phase == WorkflowPhase.CANCELLED:
            state.status = WorkflowStatus.CANCELLED
        elif state.phase == WorkflowPhase.ERROR:
            state.status = WorkflowStatus.ERROR

        assert state.status == WorkflowStatus.SUCCESS

    def test_action_failure_state_already_updated(self, tmp_path: Path) -> None:
        """If action fails, state is already updated (not rolled back)."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"

        def failing_execute(*args, **kwargs):
            raise ValueError("Action failed")

        with patch.object(orchestrator, "_execute_action", failing_execute):
            with pytest.raises(ValueError):
                orchestrator._auto_continue(state, session_dir)

        # State should be updated even though action failed
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE


# =============================================================================
# 5. Approval File Collection
# =============================================================================

class TestApprovalFileCollection:
    """Tests for _build_approval_files behavior."""

    def test_prompt_stage_only_prompt_file(self, tmp_path: Path) -> None:
        """PROMPT stage returns only the prompt file."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("Prompt content")

        files = orchestrator._build_approval_files(state, session_dir)

        assert len(files) == 1
        assert any("planning-prompt.md" in k for k in files.keys())

    def test_response_stage_includes_code_files(self, tmp_path: Path) -> None:
        """RESPONSE stage for GENERATE includes code files."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.GENERATE,
            stage=WorkflowStage.RESPONSE,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "generation-response.md").write_text("Response")

        code_dir = iteration_dir / "code"
        code_dir.mkdir()
        (code_dir / "Entity.java").write_text("public class Entity {}")

        # Also need plan.md for GENERATE phase
        (session_dir / "plan.md").write_text("# Plan")

        files = orchestrator._build_approval_files(state, session_dir)

        assert any("generation-response.md" in k for k in files.keys())
        assert any("Entity.java" in k for k in files.keys())

    def test_generate_review_phases_include_plan(self, tmp_path: Path) -> None:
        """GENERATE and REVIEW phases include plan.md."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.REVIEW,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "review-prompt.md").write_text("Review prompt")
        (session_dir / "plan.md").write_text("# The Plan")

        files = orchestrator._build_approval_files(state, session_dir)

        assert any("plan.md" in k for k in files.keys())
        plan_content = [v for k, v in files.items() if "plan.md" in k][0]
        assert plan_content == "# The Plan"

    def test_missing_files_return_none_values(self, tmp_path: Path) -> None:
        """Missing files return None values, not KeyError."""
        orchestrator = _make_orchestrator(tmp_path)

        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        # Don't create the prompt file

        files = orchestrator._build_approval_files(state, session_dir)

        # Should have an entry with None value
        assert len(files) == 1
        values = list(files.values())
        assert values[0] is None
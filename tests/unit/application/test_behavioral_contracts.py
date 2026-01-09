"""Tests for ADR-0015 behavioral contracts.

Verifies implementation-level behaviors documented in the approval providers plan.

NOTE: Updated for Phase 2 gate redesign - gates now run automatically after content
creation (CREATE_PROMPT/CALL_AI), not when user issues 'approve' command.
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
from aiwf.application.approval_config import ApprovalConfig
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.errors import ProviderError


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
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


class TestGateOrdering:
    """Contract: Approval gate runs BEFORE artifact hashing.

    Updated for Phase 2: Gates now run via _run_gate_after_action after content creation.
    """

    def test_approval_runs_before_hashing(self, tmp_path: Path) -> None:
        """Approval gate must evaluate content before hash is computed.

        Uses _run_gate_after_action directly since gates now run automatically.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            plan_approved=False,
        )
        store.load.return_value = state

        # Create response file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-response.md").write_text("# Plan content")

        config = ApprovalConfig(default_approver="skip")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Track method call order
        call_order = []

        original_run_gate = orchestrator._run_approval_gate
        # _approve_plan_response is now in ArtifactService
        original_approve_plan = orchestrator._artifact_service._approve_plan_response

        def tracked_run_gate(*args, **kwargs):
            call_order.append("approval_gate")
            return original_run_gate(*args, **kwargs)

        def tracked_approve_plan(*args, **kwargs):
            call_order.append("hash_response")
            return original_approve_plan(*args, **kwargs)

        with patch.object(orchestrator, "_run_approval_gate", tracked_run_gate):
            with patch.object(orchestrator._artifact_service, "_approve_plan_response", tracked_approve_plan):
                with patch.object(orchestrator, "_execute_action"):
                    orchestrator._run_gate_after_action(state, session_dir)

        # Approval gate must run before hashing
        assert call_order == ["approval_gate", "hash_response"]

    def test_rejection_does_not_set_plan_hash(self, tmp_path: Path) -> None:
        """Rejected content should NOT have its hash computed/stored.

        Uses _run_gate_after_action directly since gates now run automatically.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            plan_hash=None,  # No hash yet
        )
        store.load.return_value = state

        # Create response file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Plan content")

        config = ApprovalConfig(
            default_approver="claude-code",
            default_max_retries=0,  # No retries - just reject
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock approval gate to reject
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.return_value = ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Content not acceptable",
            )

            orchestrator._run_gate_after_action(state, session_dir)

        # Hash should NOT be set on rejected content
        assert state.plan_hash is None
        # Should have rejection feedback
        assert state.approval_feedback == "Content not acceptable"


class TestRetryCountLifecycle:
    """Contract: retry_count resets to 0 on stage change.

    Updated for Phase 2: Uses pending_approval to enable approve() command.
    """

    def test_retry_count_resets_on_stage_change(self, tmp_path: Path) -> None:
        """retry_count should reset when moving from PROMPT to RESPONSE stage.

        Phase 2: approve() now requires pending_approval=True to resolve.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            retry_count=3,  # Previous retries
            pending_approval=True,  # Approve resolves pending state
        )
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")

        config = ApprovalConfig(default_approver="skip")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        with patch.object(orchestrator, "_execute_action"):
            result = orchestrator.approve("test-session")

        # retry_count should be cleared after successful approval
        assert result.retry_count == 0


class TestManualApproverBehavior:
    """Contract: ManualApprovalProvider.evaluate() returns PENDING to signal pause.

    Gates run automatically after content creation. ManualApprovalProvider
    returns PENDING, which sets pending_approval=True and pauses workflow.
    User can then edit content and call 'approve' to continue.
    """

    def test_manual_approver_returns_pending_pauses_workflow(self, tmp_path: Path) -> None:
        """Manual approver returning PENDING should pause workflow, setting pending_approval.

        Gate runs, returns PENDING, workflow pauses. User can edit, then approve.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")

        config = ApprovalConfig(default_approver="manual")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Simulate gate running after content creation
        orchestrator._run_gate_after_action(state, session_dir)

        # Workflow should pause with pending_approval=True
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.pending_approval is True
        # State saved
        store.save.assert_called()


class TestMaxRetriesExhaustion:
    """Contract: When retry_count > max_retries, workflow remains IN_PROGRESS.

    Updated for Phase 2: Uses _run_gate_after_action directly.
    """

    def test_max_retries_exceeded_stays_in_progress(self, tmp_path: Path) -> None:
        """Workflow should stay IN_PROGRESS when max_retries exceeded, not ERROR.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            retry_count=0,
        )
        store.load.return_value = state

        # Create response file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Response")

        config = ApprovalConfig(
            default_approver="claude-code",
            default_max_retries=1,
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock approval gate to always reject
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            # Mock AI provider to prevent actual calls
            with patch.object(orchestrator, "_action_retry"):
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback="Always rejected",
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # Status should remain IN_PROGRESS, not ERROR
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.last_error is not None
        assert "rejected after" in state.last_error.lower()


class TestContextBuilderPattern:
    """Contract: Use base context builder with extension for approval-specific keys."""

    def test_base_context_contains_shared_keys(self) -> None:
        """Base context should include session_id, iteration, metadata."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            session_id="session-123",
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            current_iteration=2,
            metadata={"key": "value"},
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp"),
        )

        base_ctx = orchestrator._build_base_context(state)

        assert base_ctx["session_id"] == "session-123"
        assert base_ctx["iteration"] == 2
        assert base_ctx["metadata"] == {"key": "value"}

    def test_approval_context_extends_base_context(self, tmp_path: Path) -> None:
        """Approval context should include base context plus approval-specific keys."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            session_id="session-123",
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            current_iteration=2,
        )
        store.load.return_value = state

        config = ApprovalConfig(
            stages={
                "plan.prompt": {"approver": "claude-code", "allow_rewrite": True},
            }
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        session_dir = tmp_path / "session-123"
        approval_ctx = orchestrator._build_approval_context(state, session_dir)

        # Should have base context keys
        assert approval_ctx["session_id"] == "session-123"
        assert approval_ctx["iteration"] == 2

        # Should have approval-specific keys
        assert "allow_rewrite" in approval_ctx
        assert "session_dir" in approval_ctx
        assert "plan_file" in approval_ctx

    def test_provider_context_uses_base_context(self) -> None:
        """Provider context should be based on base context."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            session_id="session-123",
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            approval_feedback="Previous feedback",
            suggested_content="Suggested",
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp"),
        )

        provider_ctx = orchestrator._build_provider_context(state)

        # Should have base context keys
        assert provider_ctx["session_id"] == "session-123"
        # Should include retry-related fields when present
        assert provider_ctx["approval_feedback"] == "Previous feedback"
        assert provider_ctx["suggested_content"] == "Suggested"


class TestSuggestedContentHandling:
    """Contract: suggested_content is a hint passed to provider in retry context.

    Updated for Phase 2: Uses _run_gate_after_action directly.
    """

    def test_suggested_content_stored_in_state(self, tmp_path: Path) -> None:
        """suggested_content from approver should be stored in state.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
        )
        store.load.return_value = state

        # Create files
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Response")

        config = ApprovalConfig(
            stages={
                "plan.response": {
                    "approver": "claude-code",
                    "allow_rewrite": True,
                    "max_retries": 0,
                },
            }
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.return_value = ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Needs improvement",
                suggested_content="# Better response",
            )

            orchestrator._run_gate_after_action(state, session_dir)

        # suggested_content should be stored
        assert state.suggested_content == "# Better response"

    def test_suggested_content_included_in_context_on_retry(self) -> None:
        """suggested_content should be passed to provider context on retry."""
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            suggested_content="# Better version",
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=Path("/tmp"),
        )

        provider_ctx = orchestrator._build_provider_context(state)

        assert provider_ctx["suggested_content"] == "# Better version"


class TestPromptRegenerationCapability:
    """Contract: PROMPT rejection can auto-retry if profile declares can_regenerate_prompts.

    Updated for Phase 2: Uses _run_gate_after_action directly.
    """

    def test_profile_without_regeneration_pauses_on_prompt_rejection(
        self, tmp_path: Path
    ) -> None:
        """Profile without can_regenerate_prompts should pause workflow on rejection.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")

        config = ApprovalConfig(default_approver="claude-code")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock profile without regeneration capability
        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": False}

        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(ProfileFactory, "create", return_value=mock_profile):
                mock_gate.return_value = ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback="Needs work",
                )

                orchestrator._run_gate_after_action(state, session_dir)

        # Should not call regenerate_prompt
        mock_profile.regenerate_prompt.assert_not_called()
        # Should pause with feedback
        assert state.approval_feedback == "Needs work"

    def test_profile_with_regeneration_attempts_regeneration(
        self, tmp_path: Path
    ) -> None:
        """Profile with can_regenerate_prompts should attempt regeneration on rejection.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
        )
        store.load.return_value = state

        # Create prompt file
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Original prompt")

        config = ApprovalConfig(default_approver="claude-code")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock profile with regeneration capability
        mock_profile = Mock()
        mock_profile.get_metadata.return_value = {"can_regenerate_prompts": True}
        mock_profile.regenerate_prompt.return_value = "# Regenerated prompt"

        rejection_count = [0]

        def mock_approval_gate(*args, **kwargs):
            rejection_count[0] += 1
            if rejection_count[0] == 1:
                return ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback="Needs work",
                )
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        with patch.object(orchestrator, "_run_approval_gate", side_effect=mock_approval_gate):
            with patch.object(ProfileFactory, "create", return_value=mock_profile):
                with patch.object(orchestrator, "_execute_action"):
                    orchestrator._run_gate_after_action(state, session_dir)

        # Should have called regenerate_prompt
        mock_profile.regenerate_prompt.assert_called_once()
        # Should have succeeded on second attempt
        assert state.retry_count == 0  # Cleared after success


class TestApprovalErrorHandling:
    """Contract: Provider errors during approval keep workflow recoverable.

    Updated for Phase 2: Uses _run_gate_after_action directly.
    """

    def test_provider_exception_keeps_workflow_in_progress(self, tmp_path: Path) -> None:
        """Provider raising exception should not crash workflow or set ERROR status.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
        )
        store.load.return_value = state

        # Create files
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Response")

        config = ApprovalConfig(default_approver="claude-code")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock approval gate to raise ProviderError
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.side_effect = ProviderError("Connection failed")

            orchestrator._run_gate_after_action(state, session_dir)

        # Status should remain IN_PROGRESS (recoverable), not ERROR
        assert state.status == WorkflowStatus.IN_PROGRESS
        # Error should be recorded
        assert state.last_error is not None
        assert "Connection failed" in state.last_error

    def test_provider_timeout_keeps_workflow_in_progress(self, tmp_path: Path) -> None:
        """Provider timeout should not crash workflow or set ERROR status.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
        )
        store.load.return_value = state

        # Create files
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Response")

        config = ApprovalConfig(default_approver="claude-code")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock approval gate to raise TimeoutError
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.side_effect = TimeoutError("Provider timed out after 60s")

            orchestrator._run_gate_after_action(state, session_dir)

        # Status should remain IN_PROGRESS (recoverable)
        assert state.status == WorkflowStatus.IN_PROGRESS
        # Error should be recorded
        assert state.last_error is not None
        assert "timed out" in state.last_error.lower()

    def test_malformed_response_defaults_to_rejection(self, tmp_path: Path) -> None:
        """Unparseable approval response should default to REJECTED, not crash.

        Phase 2: Gates run via _run_gate_after_action after content creation.
        """
        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
        )
        store.load.return_value = state

        # Create files
        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Response")

        config = ApprovalConfig(
            default_approver="claude-code",
            default_max_retries=0,
        )

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # Mock approval gate to return malformed/ambiguous response
        # This simulates what AIApprovalProvider does with unparseable AI output
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            # Malformed response defaults to REJECTED per Response Parsing contract
            mock_gate.return_value = ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Unable to parse approval response",
            )

            orchestrator._run_gate_after_action(state, session_dir)

        # Should be rejected (safe default), not error
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.approval_feedback is not None
        assert "parse" in state.approval_feedback.lower()


class TestApproveRejectIdempotence:
    """Contract: approve/reject when not pending raises InvalidCommand.

    Only one of approve/reject can succeed when pending. Calling either
    when not pending should raise an error, not silently succeed.
    """

    def test_approve_when_not_pending_raises_error(self, tmp_path: Path) -> None:
        """approve() when pending_approval=False raises InvalidCommand."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=False,  # Not pending
        )
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with pytest.raises(InvalidCommand) as exc_info:
            orchestrator.approve("test-session")

        assert "no pending approval" in str(exc_info.value).lower()

    def test_reject_when_not_pending_raises_error(self, tmp_path: Path) -> None:
        """reject() when pending_approval=False raises InvalidCommand."""
        from aiwf.application.workflow_orchestrator import InvalidCommand

        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=False,  # Not pending
        )
        store.load.return_value = state

        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
        )

        with pytest.raises(InvalidCommand) as exc_info:
            orchestrator.reject("test-session", feedback="Rejected")

        assert "no pending approval" in str(exc_info.value).lower()


class TestPendingApprovalPersistence:
    """Contract: pending_approval survives state save/load cycle.

    When workflow pauses with pending_approval=True, reloading the state
    should preserve this flag so the user can resume with approve/reject.
    """

    def test_pending_approval_persists_across_save_load(self, tmp_path: Path) -> None:
        """pending_approval=True survives JSON serialization round-trip."""
        from aiwf.domain.persistence.session_store import SessionStore

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()
        store = SessionStore(sessions_root)

        # Create state with pending_approval
        state = _make_state(
            session_id="persist-test",
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.PROMPT,
            pending_approval=True,
            approval_feedback="Awaiting user review",
        )

        # Save
        store.save(state)

        # Load
        loaded = store.load("persist-test")

        # pending_approval should be preserved
        assert loaded.pending_approval is True
        assert loaded.approval_feedback == "Awaiting user review"


class TestGateErrorRetry:
    """Contract: Gate errors are recoverable via approve() retry.

    When a gate fails with an error, the workflow should remain IN_PROGRESS
    with last_error set. Calling approve() should retry the gate.
    """

    def test_gate_error_sets_last_error_and_allows_retry(self, tmp_path: Path) -> None:
        """Gate error -> last_error set -> approve() retries -> succeeds."""
        from aiwf.domain.errors import ProviderError

        store = Mock(spec=SessionStore)
        state = _make_state(
            phase=WorkflowPhase.PLAN,
            stage=WorkflowStage.RESPONSE,
            pending_approval=False,
        )
        store.load.return_value = state

        session_dir = tmp_path / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)
        (iteration_dir / "planning-prompt.md").write_text("# Prompt")
        (iteration_dir / "planning-response.md").write_text("# Response")

        config = ApprovalConfig(default_approver="skip")
        orchestrator = WorkflowOrchestrator(
            session_store=store,
            sessions_root=tmp_path,
            approval_config=config,
        )

        # First call: gate fails with error
        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            mock_gate.side_effect = ProviderError("Connection failed")
            orchestrator._run_gate_after_action(state, session_dir)

        # Should have error set
        assert state.last_error is not None
        assert "Connection failed" in state.last_error
        assert state.status == WorkflowStatus.IN_PROGRESS

        # Now simulate retry via approve() after error is fixed
        # Set pending state to allow approve (error recovery path)
        state.last_error = "Connection failed"  # Error present triggers retry

        with patch.object(orchestrator, "_run_approval_gate") as mock_gate:
            with patch.object(orchestrator, "_execute_action"):
                mock_gate.return_value = ApprovalResult(decision=ApprovalDecision.APPROVED)
                result = orchestrator.approve("test-session")

        # Should succeed - last_error cleared
        assert result.last_error is None

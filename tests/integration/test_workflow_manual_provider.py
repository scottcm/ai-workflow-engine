"""Integration tests for end-to-end workflow with manual provider.

These tests simulate the user workflow where:
1. Provider returns None (manual mode)
2. User creates response files externally
3. User calls approve/reject/retry commands

This tests the orchestrator's handling of manual workflows.
"""

import pytest
from pathlib import Path

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator, InvalidCommand
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowStage,
    WorkflowStatus,
)


@pytest.fixture
def session_with_manual_provider(
    orchestrator: WorkflowOrchestrator,
    register_integration_providers,
) -> str:
    """Create a session configured to use the manual provider."""
    session_id = orchestrator.initialize_run(
        profile="test-profile",
        providers={
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        context={"entity": "TestEntity"},
        execution_mode=ExecutionMode.INTERACTIVE,
    )
    return session_id


class TestManualWorkflowInit:
    """Tests for workflow initialization with manual provider."""

    def test_initialize_creates_session_at_init_phase(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """New session starts at INIT phase."""
        state = orchestrator.session_store.load(session_with_manual_provider)

        assert state.phase == WorkflowPhase.INIT
        assert state.stage is None
        assert state.status == WorkflowStatus.IN_PROGRESS

    def test_init_command_transitions_to_plan_prompt(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """init command transitions INIT -> PLAN[PROMPT]."""
        state = orchestrator.init(session_with_manual_provider)

        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

    def test_init_creates_planning_prompt_file(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
    ) -> None:
        """init command creates planning-prompt.md."""
        orchestrator.init(session_with_manual_provider)

        prompt_path = (
            sessions_root
            / session_with_manual_provider
            / "iteration-1"
            / "planning-prompt.md"
        )
        assert prompt_path.exists()


class TestManualWorkflowPlanPhase:
    """Tests for PLAN phase with manual provider."""

    @pytest.fixture
    def session_at_plan_prompt(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> str:
        """Session initialized and at PLAN[PROMPT]."""
        orchestrator.init(session_with_manual_provider)
        return session_with_manual_provider

    def test_approve_from_plan_prompt_transitions_to_response(
        self,
        orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
    ) -> None:
        """approve from PLAN[PROMPT] -> PLAN[RESPONSE] (calls AI)."""
        state = orchestrator.approve(session_at_plan_prompt)

        # Manual provider returns None, so we stay at RESPONSE waiting for file
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

    def test_approve_at_response_without_file_raises_error(
        self,
        orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
    ) -> None:
        """Cannot approve PLAN[RESPONSE] without response file."""
        orchestrator.approve(session_at_plan_prompt)  # -> PLAN[RESPONSE]

        with pytest.raises(ValueError, match="not found"):
            orchestrator.approve(session_at_plan_prompt)

    def test_approve_at_response_with_file_succeeds(
        self,
        orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
        sessions_root: Path,
    ) -> None:
        """Can approve PLAN[RESPONSE] when response file exists."""
        orchestrator.approve(session_at_plan_prompt)  # -> PLAN[RESPONSE]

        # Simulate user creating response file
        response_path = (
            sessions_root
            / session_at_plan_prompt
            / "iteration-1"
            / "planning-response.md"
        )
        response_path.write_text("# My Plan\n\n1. Do things\n", encoding="utf-8")

        state = orchestrator.approve(session_at_plan_prompt)

        # Should transition to GENERATE[PROMPT]
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT

    def test_plan_response_approval_sets_plan_approved_flag(
        self,
        orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
        sessions_root: Path,
    ) -> None:
        """Approving plan sets plan_approved flag and hash."""
        orchestrator.approve(session_at_plan_prompt)

        response_path = (
            sessions_root
            / session_at_plan_prompt
            / "iteration-1"
            / "planning-response.md"
        )
        response_path.write_text("# My Plan\n", encoding="utf-8")

        state = orchestrator.approve(session_at_plan_prompt)

        assert state.plan_approved is True
        assert state.plan_hash is not None


class TestManualWorkflowRejectRetry:
    """Tests for reject and retry commands."""

    @pytest.fixture
    def session_at_plan_response(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
    ) -> str:
        """Session at PLAN[RESPONSE] with response file."""
        orchestrator.init(session_with_manual_provider)
        orchestrator.approve(session_with_manual_provider)

        # Create response file
        response_path = (
            sessions_root
            / session_with_manual_provider
            / "iteration-1"
            / "planning-response.md"
        )
        response_path.write_text("# Plan\n", encoding="utf-8")

        return session_with_manual_provider

    def test_reject_stores_feedback(
        self,
        orchestrator: WorkflowOrchestrator,
        session_at_plan_response: str,
    ) -> None:
        """reject stores feedback and halts workflow."""
        state = orchestrator.reject(
            session_at_plan_response,
            feedback="Plan lacks detail on error handling",
        )

        assert state.approval_feedback == "Plan lacks detail on error handling"
        # Phase/stage unchanged
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

    def test_reject_from_prompt_raises_error(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """Cannot reject from PROMPT stage."""
        orchestrator.init(session_with_manual_provider)

        with pytest.raises(InvalidCommand, match="reject.*not valid"):
            orchestrator.reject(session_with_manual_provider, feedback="bad")

    def test_retry_triggers_regeneration(
        self,
        orchestrator: WorkflowOrchestrator,
        session_at_plan_response: str,
    ) -> None:
        """retry stores feedback and stays at RESPONSE."""
        state = orchestrator.retry(
            session_at_plan_response,
            feedback="Add more detail about testing",
        )

        assert state.approval_feedback == "Add more detail about testing"
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE


class TestManualWorkflowCancel:
    """Tests for cancel command."""

    def test_cancel_from_any_active_state(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """cancel transitions to CANCELLED from any active state."""
        orchestrator.init(session_with_manual_provider)

        state = orchestrator.cancel(session_with_manual_provider)

        assert state.phase == WorkflowPhase.CANCELLED
        assert state.stage is None
        assert state.status == WorkflowStatus.CANCELLED

    def test_cancel_from_init(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """cancel is valid even from INIT phase."""
        state = orchestrator.cancel(session_with_manual_provider)

        assert state.phase == WorkflowPhase.CANCELLED


class TestManualWorkflowFullCycle:
    """Tests for complete workflow cycles."""

    def test_full_workflow_pass(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
        mock_profile,
    ) -> None:
        """Complete workflow from INIT to COMPLETE with PASS verdict."""
        session_id = session_with_manual_provider
        session_dir = sessions_root / session_id

        # Update mock profile to return PASS verdict
        from aiwf.domain.models.processing_result import ProcessingResult
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            metadata={"verdict": "PASS"},
        )

        # INIT -> PLAN[PROMPT]
        orchestrator.init(session_id)

        # PLAN[PROMPT] -> PLAN[RESPONSE]
        orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "planning-response.md").write_text(
            "# Plan\n", encoding="utf-8"
        )

        # PLAN[RESPONSE] -> GENERATE[PROMPT]
        orchestrator.approve(session_id)
        assert (session_dir / "plan.md").exists()  # Plan copied

        # GENERATE[PROMPT] -> GENERATE[RESPONSE]
        orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "generation-response.md").write_text(
            "```java\npublic class Test {}\n```", encoding="utf-8"
        )

        # GENERATE[RESPONSE] -> REVIEW[PROMPT]
        orchestrator.approve(session_id)

        # REVIEW[PROMPT] -> REVIEW[RESPONSE]
        orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "review-response.md").write_text(
            "@@@REVIEW_META\nverdict: PASS\n@@@", encoding="utf-8"
        )

        # REVIEW[RESPONSE] -> COMPLETE (via CHECK_VERDICT)
        state = orchestrator.approve(session_id)

        assert state.phase == WorkflowPhase.COMPLETE
        assert state.stage is None
        assert state.status == WorkflowStatus.SUCCESS

    def test_workflow_with_revision_cycle(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
        mock_profile,
    ) -> None:
        """Workflow with FAIL verdict triggers revision cycle."""
        session_id = session_with_manual_provider
        session_dir = sessions_root / session_id

        # First iteration
        orchestrator.init(session_id)
        orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "planning-response.md").write_text("# Plan\n", encoding="utf-8")
        orchestrator.approve(session_id)
        orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "generation-response.md").write_text("```java\n```", encoding="utf-8")
        orchestrator.approve(session_id)
        orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "review-response.md").write_text("@@@REVIEW_META\nverdict: FAIL\n@@@", encoding="utf-8")

        # Configure mock to return FAIL first, then PASS
        from aiwf.domain.models.processing_result import ProcessingResult
        from aiwf.domain.models.write_plan import WritePlan

        # FAIL verdict
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            metadata={"verdict": "FAIL"},
        )

        # REVIEW[RESPONSE] -> REVISE[PROMPT] (FAIL verdict)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVISE
        assert state.stage == WorkflowStage.PROMPT
        assert state.current_iteration == 2  # Incremented

        # Revision cycle
        orchestrator.approve(session_id)  # -> REVISE[RESPONSE]
        (session_dir / "iteration-2" / "revision-response.md").write_text("```java\n// fixed\n```", encoding="utf-8")

        # Mock to return empty write plan for revision
        mock_profile.process_revision_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=[]),
        )

        orchestrator.approve(session_id)  # -> REVIEW[PROMPT]
        state = orchestrator.session_store.load(session_id)
        assert state.phase == WorkflowPhase.REVIEW

        orchestrator.approve(session_id)  # -> REVIEW[RESPONSE]
        (session_dir / "iteration-2" / "review-response.md").write_text("@@@REVIEW_META\nverdict: PASS\n@@@", encoding="utf-8")

        # Now configure PASS verdict
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            metadata={"verdict": "PASS"},
        )

        # REVIEW[RESPONSE] -> COMPLETE (PASS verdict)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS
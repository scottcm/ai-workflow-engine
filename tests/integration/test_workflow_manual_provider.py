"""Integration tests for end-to-end workflow with manual provider.

These tests simulate the user workflow where:
1. Provider returns None (manual mode)
2. User creates response files externally
3. User calls approve/reject commands

This tests the orchestrator's handling of manual workflows.
"""

import pytest
from pathlib import Path

from aiwf.application.approval_config import ApprovalConfig
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator, InvalidCommand
from aiwf.domain.models.workflow_state import (
    WorkflowPhase,
    WorkflowStage,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore


@pytest.fixture
def manual_orchestrator(sessions_root: Path, session_store: SessionStore) -> WorkflowOrchestrator:
    """Orchestrator with manual approvers for manual workflow tests."""
    return WorkflowOrchestrator(
        session_store=session_store,
        sessions_root=sessions_root,
        approval_config=ApprovalConfig(default_approver="manual"),
    )


@pytest.fixture
def session_with_manual_provider(
    manual_orchestrator: WorkflowOrchestrator,
    register_integration_providers,
) -> str:
    """Create a session configured to use the manual provider."""
    session_id = manual_orchestrator.initialize_run(
        profile="test-profile",
        providers={
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        context={"entity": "TestEntity"},
    )
    return session_id


class TestManualWorkflowInit:
    """Tests for workflow initialization with manual provider."""

    def test_initialize_creates_session_at_init_phase(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """New session starts at INIT phase."""
        state = manual_orchestrator.session_store.load(session_with_manual_provider)

        assert state.phase == WorkflowPhase.INIT
        assert state.stage is None
        assert state.status == WorkflowStatus.IN_PROGRESS

    def test_init_command_transitions_to_plan_prompt(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """init command transitions INIT -> PLAN[PROMPT]."""
        state = manual_orchestrator.init(session_with_manual_provider)

        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

    def test_init_creates_planning_prompt_file(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
    ) -> None:
        """init command creates planning-prompt.md."""
        manual_orchestrator.init(session_with_manual_provider)

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
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> str:
        """Session initialized and at PLAN[PROMPT]."""
        manual_orchestrator.init(session_with_manual_provider)
        return session_with_manual_provider

    def test_approve_from_plan_prompt_transitions_to_response(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
    ) -> None:
        """approve from PLAN[PROMPT] -> PLAN[RESPONSE] (calls AI)."""
        state = manual_orchestrator.approve(session_at_plan_prompt)

        # Manual provider returns None, so we stay at RESPONSE waiting for file
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

    def test_approve_at_response_without_file_raises_error(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
    ) -> None:
        """Cannot approve PLAN[RESPONSE] without response file."""
        manual_orchestrator.approve(session_at_plan_prompt)  # -> PLAN[RESPONSE]

        with pytest.raises(ValueError, match="not found"):
            manual_orchestrator.approve(session_at_plan_prompt)

    def test_approve_at_response_with_file_succeeds(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
        sessions_root: Path,
    ) -> None:
        """Can approve PLAN[RESPONSE] when response file exists."""
        manual_orchestrator.approve(session_at_plan_prompt)  # -> PLAN[RESPONSE]

        # Simulate user creating response file
        response_path = (
            sessions_root
            / session_at_plan_prompt
            / "iteration-1"
            / "planning-response.md"
        )
        response_path.write_text("# My Plan\n\n1. Do things\n", encoding="utf-8")

        state = manual_orchestrator.approve(session_at_plan_prompt)

        # Should transition to GENERATE[PROMPT]
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT

    def test_plan_response_approval_sets_plan_approved_flag(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_at_plan_prompt: str,
        sessions_root: Path,
    ) -> None:
        """Approving plan sets plan_approved flag and hash."""
        manual_orchestrator.approve(session_at_plan_prompt)

        response_path = (
            sessions_root
            / session_at_plan_prompt
            / "iteration-1"
            / "planning-response.md"
        )
        response_path.write_text("# My Plan\n", encoding="utf-8")

        state = manual_orchestrator.approve(session_at_plan_prompt)

        assert state.plan_approved is True
        assert state.plan_hash is not None


class TestManualWorkflowReject:
    """Tests for reject command."""

    @pytest.fixture
    def session_at_plan_response(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
    ) -> str:
        """Session at PLAN[RESPONSE] with response file."""
        manual_orchestrator.init(session_with_manual_provider)
        manual_orchestrator.approve(session_with_manual_provider)

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
        manual_orchestrator: WorkflowOrchestrator,
        session_at_plan_response: str,
    ) -> None:
        """reject stores feedback and halts workflow."""
        state = manual_orchestrator.reject(
            session_at_plan_response,
            feedback="Plan lacks detail on error handling",
        )

        assert state.approval_feedback == "Plan lacks detail on error handling"
        # Phase/stage unchanged
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

    def test_reject_from_prompt_pauses_for_intervention(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """Reject from PROMPT stage stores feedback and pauses for intervention."""
        manual_orchestrator.init(session_with_manual_provider)

        state = manual_orchestrator.reject(session_with_manual_provider, feedback="bad")

        # Should pause at same stage with feedback stored
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT
        assert state.approval_feedback == "bad"
        assert state.pending_approval is True


class TestManualWorkflowCancel:
    """Tests for cancel command."""

    def test_cancel_from_any_active_state(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """cancel transitions to CANCELLED from any active state."""
        manual_orchestrator.init(session_with_manual_provider)

        state = manual_orchestrator.cancel(session_with_manual_provider)

        assert state.phase == WorkflowPhase.CANCELLED
        assert state.stage is None
        assert state.status == WorkflowStatus.CANCELLED

    def test_cancel_from_init(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
    ) -> None:
        """cancel is valid even from INIT phase."""
        state = manual_orchestrator.cancel(session_with_manual_provider)

        assert state.phase == WorkflowPhase.CANCELLED


class TestManualWorkflowFullCycle:
    """Tests for complete workflow cycles."""

    def test_full_workflow_pass(
        self,
        manual_orchestrator: WorkflowOrchestrator,
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
        manual_orchestrator.init(session_id)

        # PLAN[PROMPT] -> PLAN[RESPONSE]
        manual_orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "planning-response.md").write_text(
            "# Plan\n", encoding="utf-8"
        )

        # PLAN[RESPONSE] -> GENERATE[PROMPT]
        manual_orchestrator.approve(session_id)
        assert (session_dir / "plan.md").exists()  # Plan copied

        # GENERATE[PROMPT] -> GENERATE[RESPONSE]
        manual_orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "generation-response.md").write_text(
            "```java\npublic class Test {}\n```", encoding="utf-8"
        )

        # GENERATE[RESPONSE] -> REVIEW[PROMPT]
        manual_orchestrator.approve(session_id)

        # REVIEW[PROMPT] -> REVIEW[RESPONSE]
        manual_orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "review-response.md").write_text(
            "@@@REVIEW_META\nverdict: PASS\n@@@", encoding="utf-8"
        )

        # REVIEW[RESPONSE] -> COMPLETE (via CHECK_VERDICT)
        state = manual_orchestrator.approve(session_id)

        assert state.phase == WorkflowPhase.COMPLETE
        assert state.stage is None
        assert state.status == WorkflowStatus.SUCCESS

    def test_workflow_with_revision_cycle(
        self,
        manual_orchestrator: WorkflowOrchestrator,
        session_with_manual_provider: str,
        sessions_root: Path,
        mock_profile,
    ) -> None:
        """Workflow with FAIL verdict triggers revision cycle."""
        session_id = session_with_manual_provider
        session_dir = sessions_root / session_id

        # First iteration
        manual_orchestrator.init(session_id)
        manual_orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "planning-response.md").write_text("# Plan\n", encoding="utf-8")
        manual_orchestrator.approve(session_id)
        manual_orchestrator.approve(session_id)
        (session_dir / "iteration-1" / "generation-response.md").write_text("```java\n```", encoding="utf-8")
        manual_orchestrator.approve(session_id)
        manual_orchestrator.approve(session_id)
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
        state = manual_orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVISE
        assert state.stage == WorkflowStage.PROMPT
        assert state.current_iteration == 2  # Incremented

        # Revision cycle
        manual_orchestrator.approve(session_id)  # -> REVISE[RESPONSE]
        (session_dir / "iteration-2" / "revision-response.md").write_text("```java\n// fixed\n```", encoding="utf-8")

        # Mock to return empty write plan for revision
        mock_profile.process_revision_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=[]),
        )

        manual_orchestrator.approve(session_id)  # -> REVIEW[PROMPT]
        state = manual_orchestrator.session_store.load(session_id)
        assert state.phase == WorkflowPhase.REVIEW

        manual_orchestrator.approve(session_id)  # -> REVIEW[RESPONSE]
        (session_dir / "iteration-2" / "review-response.md").write_text("@@@REVIEW_META\nverdict: PASS\n@@@", encoding="utf-8")

        # Now configure PASS verdict
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            metadata={"verdict": "PASS"},
        )

        # REVIEW[RESPONSE] -> COMPLETE (PASS verdict)
        state = manual_orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS
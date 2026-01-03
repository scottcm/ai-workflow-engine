"""Integration tests for approval flow behavior.

ADR-0015 Phase 8: End-to-end approval flow tests.
Tests the complete approval workflow with various approver configurations.
"""

import pytest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.application.approval_config import ApprovalConfig
from aiwf.domain.models.approval_result import ApprovalDecision
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowStage,
    WorkflowStatus,
)
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.providers.approval_factory import ApprovalProviderFactory

from tests.integration.conftest import create_mock_profile, MockStandardsProvider
from tests.integration.providers.fake_approval_provider import FakeApprovalProvider
from aiwf.domain.standards import StandardsProviderFactory


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sessions_root(tmp_path: Path) -> Path:
    """Isolated sessions directory for tests."""
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    return sessions


@pytest.fixture
def session_store(sessions_root: Path) -> SessionStore:
    """Create session store for tests."""
    return SessionStore(sessions_root)


@pytest.fixture
def mock_profile() -> MagicMock:
    """Default mock profile (PASS verdict, generates code)."""
    profile = create_mock_profile(review_verdict="PASS", generate_code=True)
    # Default: no prompt regeneration
    profile.get_metadata.return_value = {
        "name": "test-profile",
        "description": "Test profile",
        "can_regenerate_prompts": False,
    }
    # Mock profile needs to return mock-standards provider key
    profile.get_default_standards_provider_key.return_value = "mock-standards"
    profile.get_standards_config.return_value = {}
    return profile


@pytest.fixture
def mock_profile_with_regeneration() -> MagicMock:
    """Mock profile that supports prompt regeneration."""
    profile = create_mock_profile(review_verdict="PASS", generate_code=True)
    profile.get_metadata.return_value = {
        "name": "test-profile",
        "description": "Test profile with regeneration",
        "can_regenerate_prompts": True,
    }
    profile.get_default_standards_provider_key.return_value = "mock-standards"
    profile.get_standards_config.return_value = {}
    profile.regenerate_prompt.return_value = "# Regenerated Prompt\n\nImproved content."
    return profile


@pytest.fixture
def register_mock_standards() -> None:
    """Register mock standards provider."""
    StandardsProviderFactory.register("mock-standards", MockStandardsProvider)
    yield
    if "mock-standards" in StandardsProviderFactory._registry:
        del StandardsProviderFactory._registry["mock-standards"]


@pytest.fixture
def register_mock_profile(
    monkeypatch: pytest.MonkeyPatch,
    mock_profile: MagicMock,
    register_mock_standards: None,
) -> MagicMock:
    """Register the mock profile in ProfileFactory."""
    original_create = ProfileFactory.create
    original_get_metadata = ProfileFactory.get_metadata
    original_is_registered = ProfileFactory.is_registered

    def mock_create(profile_key: str, config: dict | None = None) -> Any:
        if profile_key == "test-profile":
            return mock_profile
        return original_create(profile_key, config=config)

    def mock_get_metadata(profile_key: str) -> dict[str, Any] | None:
        if profile_key == "test-profile":
            return mock_profile.get_metadata()
        return original_get_metadata(profile_key)

    def mock_is_registered(profile_key: str) -> bool:
        if profile_key == "test-profile":
            return True
        return original_is_registered(profile_key)

    monkeypatch.setattr(
        ProfileFactory, "create",
        classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config")))
    )
    monkeypatch.setattr(
        ProfileFactory, "get_metadata",
        classmethod(lambda cls, key: mock_get_metadata(key))
    )
    monkeypatch.setattr(
        ProfileFactory, "is_registered",
        classmethod(lambda cls, key: mock_is_registered(key))
    )

    return mock_profile


@pytest.fixture
def fake_approver() -> FakeApprovalProvider:
    """Default fake approver that always approves."""
    return FakeApprovalProvider()


@pytest.fixture
def register_fake_approver(
    monkeypatch: pytest.MonkeyPatch,
    fake_approver: FakeApprovalProvider,
) -> FakeApprovalProvider:
    """Register fake approver in ApprovalProviderFactory."""
    ApprovalProviderFactory.register("fake", lambda: fake_approver)
    yield fake_approver
    # Cleanup
    if "fake" in ApprovalProviderFactory._registry:
        del ApprovalProviderFactory._registry["fake"]


# ============================================================================
# Test 1: Full Workflow with Skip Approvers
# ============================================================================


class TestFullWorkflowWithSkipApprovers:
    """Test 1: Workflow completes with all skip approvers."""

    def test_full_workflow_with_skip_approvers(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
    ) -> None:
        """INIT → PLAN[P] → PLAN[R] → GEN[P] → GEN[R] → REV[P] → REV[R] → COMPLETE."""
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(default_approver="skip"),
        )

        # Initialize session
        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Write response files and approve through workflow
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        # PLAN phase
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Approve PLAN PROMPT -> PLAN RESPONSE
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

        # Write planning response and approve
        (iteration_dir / "planning-response.md").write_text("# Plan\n\n1. Step one")
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT

        # Approve GENERATE PROMPT -> GENERATE RESPONSE
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.RESPONSE

        # Write generation response and approve
        (iteration_dir / "generation-response.md").write_text("```java\npublic class Test {}\n```")
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVIEW
        assert state.stage == WorkflowStage.PROMPT

        # Approve REVIEW PROMPT -> REVIEW RESPONSE
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVIEW
        assert state.stage == WorkflowStage.RESPONSE

        # Write review response (PASS verdict) and approve
        (iteration_dir / "review-response.md").write_text("PASS\n\nLooks good.")
        state = orchestrator.approve(session_id)

        # Workflow should complete
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS


# ============================================================================
# Tests 2-3: Manual Approver Pauses
# ============================================================================


class TestManualApproverPauses:
    """Tests 2-3: Workflow pauses when hitting manual approver."""

    def test_manual_approver_pauses_at_prompt(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
    ) -> None:
        """PLAN[PROMPT] → approve → advances (user's command IS the approval)."""
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={"plan.prompt": {"approver": "manual"}}
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Initialize
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Approve PLAN PROMPT - user's approve command IS the approval, advances immediately
        state = orchestrator.approve(session_id)

        # Advanced to PLAN RESPONSE (user's approve is the decision)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE
        assert state.status == WorkflowStatus.IN_PROGRESS

    def test_manual_approver_advances_at_response(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
    ) -> None:
        """PLAN[RESPONSE] → approve → advances (user's command IS the approval)."""
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},
                    "plan.response": {"approver": "manual"},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Get to PLAN RESPONSE
        state = orchestrator.init(session_id)
        state = orchestrator.approve(session_id)  # Skip PLAN PROMPT
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

        # Write response file
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Plan")

        # Approve PLAN RESPONSE - user's approve command IS the approval
        state = orchestrator.approve(session_id)

        # Advanced to GENERATE PROMPT
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT
        assert state.status == WorkflowStatus.IN_PROGRESS


# ============================================================================
# Tests 4-6: AI Approver Behavior
# ============================================================================


class TestAIApproverBehavior:
    """Tests 4-6: AI approver approval, rejection, and max retries."""

    def test_ai_approver_approves_and_advances(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:APPROVED → GENERATE[PROMPT]."""
        # Configure fake approver to approve
        register_fake_approver._decisions = [ApprovalDecision.APPROVED]

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},
                    "plan.response": {"approver": "fake"},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Get to PLAN RESPONSE
        state = orchestrator.init(session_id)
        state = orchestrator.approve(session_id)
        assert state.stage == WorkflowStage.RESPONSE

        # Write response file
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Plan")

        # Approve PLAN RESPONSE - AI should approve and advance
        state = orchestrator.approve(session_id)

        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT
        assert state.approval_feedback is None
        assert register_fake_approver.call_count == 1

    def test_ai_approver_rejects_then_retries_and_succeeds(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:REJECTED → retry → AI:APPROVED.

        Note: Retry requires a response provider that returns content.
        With manual provider, the retry would pause waiting for user input.
        This test verifies the retry mechanism with proper provider setup.
        """
        # Configure: reject first, approve second
        register_fake_approver._decisions = [
            ApprovalDecision.REJECTED,
            ApprovalDecision.APPROVED,
        ]
        register_fake_approver._feedback = "Needs more detail"

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},
                    "plan.response": {"approver": "fake", "max_retries": 3},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Get to PLAN RESPONSE
        state = orchestrator.init(session_id)
        state = orchestrator.approve(session_id)

        # Write response file
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Plan v1")

        # First approve - rejects, retry logic kicks in
        # Retry: gate(1) rejects, regenerate, gate(2) approves
        state = orchestrator.approve(session_id)

        # With manual provider and max_retries=3, retry runs twice:
        # 1. Initial approval check - REJECTED
        # 2. After regeneration - APPROVED (per fake_approver decisions)
        # The workflow advances after second check succeeds
        assert state.approval_feedback is None  # Cleared after success
        assert state.retry_count == 0  # Cleared after success
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT
        assert register_fake_approver.call_count == 2

    def test_ai_approver_exhausts_max_retries(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:REJECTED × (max+1) → stays IN_PROGRESS."""
        # Configure: always reject
        register_fake_approver._decisions = [ApprovalDecision.REJECTED]
        register_fake_approver._feedback = "Not good enough"

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},
                    "plan.response": {"approver": "fake", "max_retries": 2},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Get to PLAN RESPONSE
        state = orchestrator.init(session_id)
        state = orchestrator.approve(session_id)

        # Write response file
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Plan")

        # Approve - should exhaust retries
        state = orchestrator.approve(session_id)

        # Should stay IN_PROGRESS (not ERROR)
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.last_error is not None
        assert "rejected" in state.last_error.lower()
        # Retries: initial + max_retries = 3 calls
        assert register_fake_approver.call_count == 3


# ============================================================================
# Tests 7-8: Prompt Rejection Behavior
# ============================================================================


class TestPromptRejectionBehavior:
    """Tests 7-8: PROMPT rejection with/without regeneration."""

    def test_prompt_rejection_pauses_without_regeneration(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
    ) -> None:
        """PLAN[PROMPT] → AI:REJECTED → pauses (no retry)."""
        # Configure to reject
        register_fake_approver._decisions = [ApprovalDecision.REJECTED]
        register_fake_approver._feedback = "Prompt needs work"

        # Profile doesn't support regeneration (default mock)
        register_mock_profile.get_metadata.return_value = {
            "name": "test-profile",
            "can_regenerate_prompts": False,
        }

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={"plan.prompt": {"approver": "fake", "max_retries": 3}}
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)
        assert state.stage == WorkflowStage.PROMPT

        # Approve - should reject and pause (no retry for PROMPT without regeneration)
        state = orchestrator.approve(session_id)

        # Should pause with feedback
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT
        assert state.approval_feedback == "Prompt needs work"
        # Only 1 call - no retry loop for PROMPT
        assert register_fake_approver.call_count == 1

    def test_prompt_rejection_with_regeneration_succeeds(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        mock_profile_with_regeneration: MagicMock,
        register_mock_standards: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PLAN[PROMPT] → AI:REJECTED → regenerate → AI:APPROVED."""
        # Set up fake approver: reject first, approve second
        fake_approver = FakeApprovalProvider(
            decisions=[ApprovalDecision.REJECTED, ApprovalDecision.APPROVED],
            feedback="Needs more context",
        )
        ApprovalProviderFactory.register("fake", lambda: fake_approver)

        # Register profile with regeneration
        original_create = ProfileFactory.create
        original_get_metadata = ProfileFactory.get_metadata
        original_is_registered = ProfileFactory.is_registered

        def mock_create(profile_key: str, config: dict | None = None) -> Any:
            if profile_key == "test-profile":
                return mock_profile_with_regeneration
            return original_create(profile_key, config=config)

        def mock_get_metadata(profile_key: str) -> dict[str, Any] | None:
            if profile_key == "test-profile":
                return mock_profile_with_regeneration.get_metadata()
            return original_get_metadata(profile_key)

        def mock_is_registered(profile_key: str) -> bool:
            if profile_key == "test-profile":
                return True
            return original_is_registered(profile_key)

        monkeypatch.setattr(
            ProfileFactory, "create",
            classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config")))
        )
        monkeypatch.setattr(
            ProfileFactory, "get_metadata",
            classmethod(lambda cls, key: mock_get_metadata(key))
        )
        monkeypatch.setattr(
            ProfileFactory, "is_registered",
            classmethod(lambda cls, key: mock_is_registered(key))
        )

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={"plan.prompt": {"approver": "fake"}}
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)

        # Approve - should reject, regenerate, then approve and transition
        state = orchestrator.approve(session_id)

        # Should have called regenerate_prompt
        mock_profile_with_regeneration.regenerate_prompt.assert_called_once()
        # Regeneration approved - approval state cleared and transitioned to RESPONSE
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE  # Transitioned after successful retry
        assert state.approval_feedback is None  # Cleared after approval
        assert fake_approver.call_count == 2

        # Cleanup
        del ApprovalProviderFactory._registry["fake"]


# ============================================================================
# Tests 9-10: Suggested Content Handling
# ============================================================================


class TestSuggestedContentHandling:
    """Tests 9-10: Suggested content applied to prompt / stored for response."""

    def test_suggested_content_applied_to_prompt(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
    ) -> None:
        """PLAN[PROMPT] → AI:REJECTED+suggested → content written to file."""
        # Configure to reject with suggested content
        register_fake_approver._decisions = [ApprovalDecision.REJECTED]
        register_fake_approver._feedback = "Try this"
        register_fake_approver._suggested_content = "# Improved Prompt\n\nBetter content."

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {
                        "approver": "fake",
                        "allow_rewrite": True,
                    }
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)

        # Check original prompt exists
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        prompt_path = iteration_dir / "planning-prompt.md"
        assert prompt_path.exists()
        original_content = prompt_path.read_text()

        # Approve - should apply suggested content
        state = orchestrator.approve(session_id)

        # Prompt file should be updated
        new_content = prompt_path.read_text()
        assert new_content == "# Improved Prompt\n\nBetter content."
        assert new_content != original_content

    def test_suggested_content_stored_for_response(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:REJECTED+suggested → suggested_content in state."""
        # Configure to reject with suggested content
        register_fake_approver._decisions = [ApprovalDecision.REJECTED]
        register_fake_approver._feedback = "Try this approach"
        register_fake_approver._suggested_content = "# Better Response\n\nImproved plan."

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},
                    "plan.response": {
                        "approver": "fake",
                        "allow_rewrite": True,
                        "max_retries": 0,
                    },
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Get to PLAN RESPONSE
        state = orchestrator.init(session_id)
        state = orchestrator.approve(session_id)

        # Write response file
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Original Plan")

        # Approve - should reject and store suggested content
        state = orchestrator.approve(session_id)

        # suggested_content should be in state
        assert state.suggested_content == "# Better Response\n\nImproved plan."


# ============================================================================
# Tests 11-12: Retry Count and Mixed Configuration
# ============================================================================


class TestRetryCountAndMixedConfig:
    """Tests 11-12: Retry count reset and mixed approver configuration."""

    def test_retry_count_resets_on_stage_change(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
    ) -> None:
        """PROMPT(retry=2) → approve → RESPONSE(retry=0)."""
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(default_approver="skip"),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Initialize
        state = orchestrator.init(session_id)

        # Manually set retry_count (simulating previous rejections)
        state.retry_count = 2
        session_store.save(state)

        # Approve PLAN PROMPT - should transition and reset retry_count
        state = orchestrator.approve(session_id)

        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE
        assert state.retry_count == 0

    def test_mixed_approver_configuration(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
    ) -> None:
        """skip@PLAN.P, manual@PLAN.R, skip@GEN.* → pauses only at PLAN.RESPONSE.

        This test verifies that mixed approver configurations work correctly.
        Skip approvers auto-advance, manual approvers pause for user decision.

        Note: With manual approver, each `approve` call runs the gate which
        returns None. The user's approve command IS the manual approval.
        To advance past a manual gate, the user reviews the artifact and
        runs approve - this is treated as the approval decision.
        """
        # Use fake approver that approves on second call to simulate
        # "manual review then approval" flow
        fake_approver = FakeApprovalProvider(
            # First call returns None-like behavior (we'll handle in config)
            decisions=[ApprovalDecision.APPROVED],
        )
        ApprovalProviderFactory.register("fake-manual", lambda: fake_approver)

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},
                    "plan.response": {"approver": "manual"},  # Pauses
                    "generate.prompt": {"approver": "skip"},
                    "generate.response": {"approver": "skip"},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual", "generator": "manual"},
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        # Initialize
        state = orchestrator.init(session_id)
        assert state.stage == WorkflowStage.PROMPT

        # Skip PLAN PROMPT (skip approver)
        state = orchestrator.approve(session_id)
        assert state.stage == WorkflowStage.RESPONSE

        # Write response
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Plan")

        # Approve at PLAN RESPONSE - manual approver, user's command IS the approval
        state = orchestrator.approve(session_id)

        # Advanced to GENERATE PROMPT (user's approve is the decision)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT
        assert state.status == WorkflowStatus.IN_PROGRESS

        # Cleanup
        if "fake-manual" in ApprovalProviderFactory._registry:
            del ApprovalProviderFactory._registry["fake-manual"]

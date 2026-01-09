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
from tests.integration.providers.fake_ai_provider import FakeAIProvider
from aiwf.domain.standards import StandardsProviderFactory
from aiwf.domain.providers.provider_factory import AIProviderFactory


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


@pytest.fixture
def fake_ai_provider() -> FakeAIProvider:
    """Fake AI provider that returns deterministic responses."""
    return FakeAIProvider(review_verdict="PASS")


@pytest.fixture
def register_fake_ai_provider(fake_ai_provider: FakeAIProvider) -> FakeAIProvider:
    """Register fake AI provider in AIProviderFactory."""
    AIProviderFactory.register("fake-ai", lambda: fake_ai_provider)
    yield fake_ai_provider
    # Cleanup
    if "fake-ai" in AIProviderFactory._registry:
        del AIProviderFactory._registry["fake-ai"]


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
        """INIT → PLAN[P] → PLAN[R] → GEN[P] → GEN[R] → REV[P] → REV[R] → COMPLETE.

        Uses manual approver for PROMPT stages to allow stepping through,
        and skip approver for RESPONSE stages to auto-advance after file write.
        """
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    # Manual for PROMPT stages (to step through)
                    "plan.prompt": {"approver": "manual"},
                    "plan.response": {"approver": "skip"},
                    "generate.prompt": {"approver": "manual"},
                    "generate.response": {"approver": "skip"},
                    "review.prompt": {"approver": "manual"},
                    "review.response": {"approver": "skip"},
                }
            ),
        )

        # Initialize session
        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual"},
            context={"entity": "TestEntity"},
        )

        # Write response files and approve through workflow
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)

        # PLAN phase
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Write PLAN response BEFORE approving PROMPT (skip approver at RESPONSE needs file to exist)
        (iteration_dir / "planning-response.md").write_text("# Plan\n\n1. Step one")

        # Approve PLAN PROMPT -> skip auto-advances through RESPONSE to GENERATE PROMPT
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT

        # Write GENERATE response BEFORE approving PROMPT
        (iteration_dir / "generation-response.md").write_text("```java\npublic class Test {}\n```")

        # Approve GENERATE PROMPT -> skip auto-advances through RESPONSE to REVIEW PROMPT
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVIEW
        assert state.stage == WorkflowStage.PROMPT

        # Write REVIEW response BEFORE approving PROMPT
        (iteration_dir / "review-response.md").write_text("PASS\n\nLooks good.")

        # Approve REVIEW PROMPT -> skip auto-advances through RESPONSE to COMPLETE
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
                    "plan.prompt": {"approver": "manual"},  # Manual to control stepping
                    "plan.response": {"approver": "manual"},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
        )

        # Get to PLAN RESPONSE
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        state = orchestrator.approve(session_id)  # Manual approve PLAN PROMPT
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
    """Tests 4-6+: AI approver approval, rejection, and max retries."""

    def test_ai_approver_approves_prompt_and_advances(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
    ) -> None:
        """PLAN[PROMPT] → skip:APPROVED → PLAN[RESPONSE].

        Tests the happy path where approver approves prompt immediately.
        Uses skip approver which returns APPROVED - from engine's perspective,
        APPROVED is APPROVED regardless of source.
        """
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},  # Auto-approve
                    "plan.response": {"approver": "manual"},  # Pause to verify we reached RESPONSE
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
        )

        # Initialize - skip at plan.prompt auto-approves, advances to RESPONSE
        state = orchestrator.init(session_id)

        # Should have advanced to PLAN RESPONSE (skip approved the prompt)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.approval_feedback is None

    def test_ai_approver_approves_response_and_advances(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
        register_fake_ai_provider: FakeAIProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:APPROVED → GENERATE[PROMPT].

        Uses FakeAIProvider so response is created when CALL_AI runs.
        Gate runs immediately after with FakeApprovalProvider.
        """
        # Configure fake approver to approve
        register_fake_approver._decisions = [ApprovalDecision.APPROVED]

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "manual"},  # Manual to control stepping
                    "plan.response": {"approver": "fake"},  # AI approver evaluates response
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "fake-ai"},  # FakeAIProvider creates response
            context={"entity": "TestEntity"},
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Approve PLAN PROMPT → transitions to RESPONSE → CALL_AI runs →
        # FakeAIProvider creates response → gate runs → FakeApprovalProvider approves →
        # auto-continues to GENERATE PROMPT
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
        register_fake_ai_provider: FakeAIProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:REJECTED → retry → AI:APPROVED.

        Uses FakeAIProvider so retry can regenerate response.
        Gate runs after each CALL_AI with FakeApprovalProvider.
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
                    "plan.prompt": {"approver": "manual"},  # Manual to control stepping
                    "plan.response": {"approver": "fake", "max_retries": 3},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "fake-ai"},  # FakeAIProvider for retry
            context={"entity": "TestEntity"},
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Approve PLAN PROMPT → transitions to RESPONSE → CALL_AI runs →
        # FakeAIProvider creates response → gate runs → REJECTED →
        # retry: CALL_AI again → gate runs → APPROVED → auto-continues
        state = orchestrator.approve(session_id)

        # Retry succeeded, workflow advanced
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
        register_fake_ai_provider: FakeAIProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:REJECTED × (max+1) → stays IN_PROGRESS.

        Uses FakeAIProvider so retry can regenerate response.
        FakeApprovalProvider always rejects until max_retries exhausted.
        """
        # Configure: always reject
        register_fake_approver._decisions = [ApprovalDecision.REJECTED]
        register_fake_approver._feedback = "Not good enough"

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "manual"},  # Manual to control stepping
                    "plan.response": {"approver": "fake", "max_retries": 2},
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "fake-ai"},  # FakeAIProvider for retry
            context={"entity": "TestEntity"},
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Approve PLAN PROMPT → transitions to RESPONSE → CALL_AI runs →
        # FakeAIProvider creates response → gate runs → REJECTED →
        # retry loop exhausts max_retries
        state = orchestrator.approve(session_id)

        # Should stay IN_PROGRESS with error (not ERROR status)
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
        """PLAN[PROMPT] → AI:REJECTED → pauses with feedback.

        Gate runs during init() after CREATE_PROMPT action.
        When rejected and profile can't regenerate, workflow pauses with feedback.
        Note: Calling approve() would mean "proceed anyway" and advance.
        """
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
        )

        # Initialize - gate runs after CREATE_PROMPT, fake approver rejects
        state = orchestrator.init(session_id)

        # Should be paused at PROMPT with feedback (not advanced)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT
        assert state.pending_approval is True
        assert state.approval_feedback == "Prompt needs work"
        # Only 1 call - no retry loop for PROMPT without regeneration
        assert register_fake_approver.call_count == 1

    def test_prompt_rejection_with_regeneration_succeeds(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        mock_profile_with_regeneration: MagicMock,
        register_mock_standards: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PLAN[PROMPT] → AI:REJECTED → regenerate → AI:APPROVED → RESPONSE.

        Gate runs during init() after CREATE_PROMPT.
        When rejected and profile CAN regenerate:
        1. Profile regenerates prompt
        2. Gate re-runs with new prompt
        3. Approved on second try → auto-continues to RESPONSE
        """
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
                stages={
                    "plan.prompt": {"approver": "fake"},
                    "plan.response": {"approver": "manual"},  # Pause at RESPONSE
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
        )

        # Initialize - gate runs after CREATE_PROMPT:
        # 1. Fake approver rejects → profile regenerates → gate re-runs → approves
        # 2. Auto-continues to RESPONSE (pauses due to manual approver)
        state = orchestrator.init(session_id)

        # Should have called regenerate_prompt during init's gate handling
        mock_profile_with_regeneration.regenerate_prompt.assert_called_once()

        # Should be at RESPONSE after successful regeneration+approval
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE
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
        """PLAN[PROMPT] → AI:REJECTED+suggested → content written to file.

        Gate runs during init() after CREATE_PROMPT.
        When rejected with suggested_content and allow_rewrite=True,
        the suggested content is written to the prompt file immediately.
        """
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
        )

        # Initialize - gate runs after CREATE_PROMPT, fake approver rejects with suggestion
        # Suggested content is written to file during init()
        state = orchestrator.init(session_id)

        # Verify prompt file was updated with suggested content
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        prompt_path = iteration_dir / "planning-prompt.md"
        assert prompt_path.exists()

        content = prompt_path.read_text()
        assert content == "# Improved Prompt\n\nBetter content."

        # State should have pending_approval and feedback
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT
        assert state.pending_approval is True
        assert state.approval_feedback == "Try this"

    def test_suggested_content_stored_for_response(
        self,
        sessions_root: Path,
        session_store: SessionStore,
        register_mock_profile: MagicMock,
        register_fake_approver: FakeApprovalProvider,
        register_fake_ai_provider: FakeAIProvider,
    ) -> None:
        """PLAN[RESPONSE] → AI:REJECTED+suggested → suggested_content in state.

        Uses FakeAIProvider so response exists when gate runs.
        FakeApprovalProvider rejects with suggested_content.
        """
        # Configure to reject with suggested content
        register_fake_approver._decisions = [ApprovalDecision.REJECTED]
        register_fake_approver._feedback = "Try this approach"
        register_fake_approver._suggested_content = "# Better Response\n\nImproved plan."

        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "manual"},  # Manual to control stepping
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
            providers={"planner": "fake-ai"},  # FakeAIProvider creates response
            context={"entity": "TestEntity"},
        )

        # Initialize to PLAN PROMPT
        state = orchestrator.init(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.PROMPT

        # Approve PLAN PROMPT → transitions to RESPONSE → CALL_AI runs →
        # FakeAIProvider creates response → gate runs → REJECTED with suggested_content
        state = orchestrator.approve(session_id)

        # suggested_content should be in state
        assert state.suggested_content == "# Better Response\n\nImproved plan."
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE  # Stays at RESPONSE (rejected, no retry)


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
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "manual"},  # Manual to control stepping
                    "plan.response": {"approver": "manual"},  # Manual to pause at RESPONSE
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual"},
            context={"entity": "TestEntity"},
        )

        # Initialize
        state = orchestrator.init(session_id)
        assert state.stage == WorkflowStage.PROMPT

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
        """skip@PLAN.P, manual@PLAN.R, manual@GEN.P → skip auto-advances, manual pauses.

        This test verifies that mixed approver configurations work correctly.
        Skip approvers auto-advance, manual approvers pause for user decision.

        With skip at plan.prompt: init() auto-continues through PROMPT to RESPONSE.
        With manual at plan.response: workflow pauses waiting for user approval.
        After approval: advances to GENERATE.PROMPT (pauses for manual approver).
        """
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=sessions_root,
            approval_config=ApprovalConfig(
                stages={
                    "plan.prompt": {"approver": "skip"},  # Auto-continue
                    "plan.response": {"approver": "manual"},  # Pauses
                    "generate.prompt": {"approver": "manual"},  # Pauses
                }
            ),
        )

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={"planner": "manual", "generator": "manual"},
            context={"entity": "TestEntity"},
        )

        # Initialize - skip at plan.prompt auto-continues to RESPONSE
        state = orchestrator.init(session_id)
        # With skip at plan.prompt, init auto-continues past PROMPT to RESPONSE
        # (pauses at RESPONSE because manual approver there)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE  # Auto-continued to here

        # Write response (we're already at RESPONSE stage)
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Plan")

        # Approve at PLAN RESPONSE - manual approver, user's command IS the approval
        state = orchestrator.approve(session_id)

        # Advanced to GENERATE PROMPT (pauses for manual approver there)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT
        assert state.status == WorkflowStatus.IN_PROGRESS

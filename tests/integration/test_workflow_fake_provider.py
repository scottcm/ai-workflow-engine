"""Integration tests for end-to-end workflow with fake provider.

These tests simulate automated workflows where:
1. Provider returns deterministic responses
2. Test calls approve commands to advance workflow
3. Response files are created automatically by the provider

This tests the orchestrator's handling of automated AI responses.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowStage,
    WorkflowStatus,
)
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.providers.provider_factory import AIProviderFactory

from tests.integration.providers.fake_ai_provider import FakeAIProvider


@pytest.fixture
def fake_provider_pass() -> FakeAIProvider:
    """Fake provider that returns PASS verdict for reviews."""
    return FakeAIProvider(review_verdict="PASS")


@pytest.fixture
def fake_provider_fail() -> FakeAIProvider:
    """Fake provider that returns FAIL verdict for reviews."""
    return FakeAIProvider(review_verdict="FAIL")


@pytest.fixture
def register_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    fake_provider_pass: FakeAIProvider,
    register_integration_providers,
) -> FakeAIProvider:
    """Register the fake provider and return it for assertions."""
    AIProviderFactory.register("fake", lambda: fake_provider_pass)
    return fake_provider_pass


@pytest.fixture
def session_with_fake_provider(
    orchestrator: WorkflowOrchestrator,
    register_fake_provider: FakeAIProvider,
) -> str:
    """Create a session configured to use the fake provider."""
    session_id = orchestrator.initialize_run(
        profile="test-profile",
        providers={
            "planner": "fake",
            "generator": "fake",
            "reviewer": "fake",
            "reviser": "fake",
        },
        context={"entity": "TestEntity"},
        execution_mode=ExecutionMode.AUTOMATED,
    )
    return session_id


class TestFakeProviderBasics:
    """Basic tests for fake provider behavior."""

    def test_fake_provider_returns_deterministic_response(
        self,
        fake_provider_pass: FakeAIProvider,
    ) -> None:
        """Fake provider returns non-None response."""
        response = fake_provider_pass.generate("test prompt", {})
        assert response is not None
        assert isinstance(response, str)

    def test_fake_provider_tracks_call_history(
        self,
        fake_provider_pass: FakeAIProvider,
    ) -> None:
        """Fake provider records calls for assertions."""
        fake_provider_pass.generate("prompt 1", {"ctx": 1})
        fake_provider_pass.generate("prompt 2", {"ctx": 2})

        assert len(fake_provider_pass.call_history) == 2
        assert fake_provider_pass.call_history[0][0] == "prompt 1"
        assert fake_provider_pass.call_history[1][0] == "prompt 2"


class TestFakeProviderWorkflow:
    """Tests for workflow with fake provider."""

    def test_approve_from_prompt_creates_response_file(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_fake_provider: str,
        sessions_root: Path,
        register_fake_provider: FakeAIProvider,
    ) -> None:
        """Approving PROMPT stage with fake provider creates response file."""
        session_id = session_with_fake_provider

        orchestrator.init(session_id)
        state = orchestrator.approve(session_id)  # PLAN[PROMPT] -> PLAN[RESPONSE]

        response_path = (
            sessions_root
            / session_id
            / "iteration-1"
            / "planning-response.md"
        )
        assert response_path.exists()
        assert "Implementation Plan" in response_path.read_text(encoding="utf-8")

    def test_fake_provider_receives_prompt_content(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_fake_provider: str,
        register_fake_provider: FakeAIProvider,
    ) -> None:
        """Fake provider receives actual prompt content."""
        session_id = session_with_fake_provider
        provider = register_fake_provider

        orchestrator.init(session_id)
        orchestrator.approve(session_id)  # Calls provider

        assert len(provider.call_history) == 1
        prompt = provider.call_history[0][0]
        assert "Planning Prompt" in prompt or "planning-response" in prompt


class TestFakeProviderFullWorkflow:
    """Tests for complete workflow with fake provider."""

    def test_full_workflow_automated_pass(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_fake_provider: str,
        sessions_root: Path,
        mock_profile: MagicMock,
    ) -> None:
        """Complete automated workflow with PASS verdict."""
        session_id = session_with_fake_provider

        # Configure mock profile
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            metadata={"verdict": "PASS"},
        )

        # INIT -> PLAN[PROMPT]
        orchestrator.init(session_id)

        # PLAN[PROMPT] -> PLAN[RESPONSE] (provider creates file)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

        # PLAN[RESPONSE] -> GENERATE[PROMPT]
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.PROMPT

        # GENERATE[PROMPT] -> GENERATE[RESPONSE] (provider creates file)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.GENERATE
        assert state.stage == WorkflowStage.RESPONSE

        # GENERATE[RESPONSE] -> REVIEW[PROMPT]
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVIEW
        assert state.stage == WorkflowStage.PROMPT

        # REVIEW[PROMPT] -> REVIEW[RESPONSE] (provider creates file)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVIEW
        assert state.stage == WorkflowStage.RESPONSE

        # REVIEW[RESPONSE] -> COMPLETE (CHECK_VERDICT with PASS)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS

    def test_full_workflow_with_revision(
        self,
        orchestrator: WorkflowOrchestrator,
        sessions_root: Path,
        register_integration_providers,
        fake_provider_fail: FakeAIProvider,
        mock_profile: MagicMock,
    ) -> None:
        """Complete workflow with FAIL verdict triggers revision."""
        # Register FAIL provider
        AIProviderFactory.register("fake-fail", lambda: fake_provider_fail)

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={
                "planner": "fake-fail",
                "generator": "fake-fail",
                "reviewer": "fake-fail",
                "reviser": "fake-fail",
            },
            context={"entity": "TestEntity"},
            execution_mode=ExecutionMode.AUTOMATED,
        )

        # Run through to first review
        orchestrator.init(session_id)
        orchestrator.approve(session_id)  # PLAN[PROMPT] -> PLAN[RESPONSE]
        orchestrator.approve(session_id)  # PLAN[RESPONSE] -> GENERATE[PROMPT]
        orchestrator.approve(session_id)  # GENERATE[PROMPT] -> GENERATE[RESPONSE]
        orchestrator.approve(session_id)  # GENERATE[RESPONSE] -> REVIEW[PROMPT]
        orchestrator.approve(session_id)  # REVIEW[PROMPT] -> REVIEW[RESPONSE]

        # Configure FAIL verdict
        mock_profile.process_review_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            metadata={"verdict": "FAIL"},
        )

        # REVIEW[RESPONSE] -> REVISE[PROMPT] (FAIL verdict)
        state = orchestrator.approve(session_id)
        assert state.phase == WorkflowPhase.REVISE
        assert state.stage == WorkflowStage.PROMPT
        assert state.current_iteration == 2

        # Continue revision cycle
        orchestrator.approve(session_id)  # REVISE[PROMPT] -> REVISE[RESPONSE]
        state = orchestrator.session_store.load(session_id)
        assert state.phase == WorkflowPhase.REVISE
        assert state.stage == WorkflowStage.RESPONSE


class TestFakeProviderRetry:
    """Tests for retry with fake provider."""

    def test_retry_regenerates_response(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_fake_provider: str,
        sessions_root: Path,
        register_fake_provider: FakeAIProvider,
    ) -> None:
        """retry regenerates response using fake provider."""
        session_id = session_with_fake_provider
        provider = register_fake_provider

        orchestrator.init(session_id)
        orchestrator.approve(session_id)  # PLAN[PROMPT] -> PLAN[RESPONSE]

        # Provider called once
        assert len(provider.call_history) == 1

        # Retry
        state = orchestrator.retry(session_id, feedback="Add more detail")

        # Provider called again
        assert len(provider.call_history) == 2

        # State stays at RESPONSE
        assert state.phase == WorkflowPhase.PLAN
        assert state.stage == WorkflowStage.RESPONSE

    def test_retry_passes_feedback_in_context(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_fake_provider: str,
        register_fake_provider: FakeAIProvider,
    ) -> None:
        """retry stores feedback for provider context."""
        session_id = session_with_fake_provider

        orchestrator.init(session_id)
        orchestrator.approve(session_id)
        orchestrator.retry(session_id, feedback="Be more specific")

        # Verify feedback is stored
        state = orchestrator.session_store.load(session_id)
        assert state.approval_feedback == "Be more specific"


class TestFakeProviderCustomResponses:
    """Tests for fake provider with custom responses."""

    def test_custom_phase_responses(
        self,
        orchestrator: WorkflowOrchestrator,
        sessions_root: Path,
        register_integration_providers,
    ) -> None:
        """Fake provider can be configured with custom per-phase responses."""
        custom_provider = FakeAIProvider(
            phase_responses={
                WorkflowPhase.PLAN: "# Custom Plan\n\nMy custom planning response.",
            }
        )
        AIProviderFactory.register("custom", lambda: custom_provider)

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={
                "planner": "custom",
                "generator": "fake",
                "reviewer": "fake",
                "reviser": "fake",
            },
            context={"entity": "TestEntity"},
        )

        orchestrator.init(session_id)
        orchestrator.approve(session_id)

        response_path = (
            sessions_root
            / session_id
            / "iteration-1"
            / "planning-response.md"
        )
        content = response_path.read_text(encoding="utf-8")
        assert "Custom Plan" in content
        assert "My custom planning response" in content

    def test_custom_generator_function(
        self,
        orchestrator: WorkflowOrchestrator,
        sessions_root: Path,
        register_integration_providers,
    ) -> None:
        """Fake provider can use custom generator function."""
        def my_generator(prompt: str, context: dict | None) -> str:
            entity = context.get("entity", "Unknown") if context else "Unknown"
            return f"# Generated for {entity}\n\nCustom response."

        custom_provider = FakeAIProvider(generator=my_generator)
        AIProviderFactory.register("generator-fn", lambda: custom_provider)

        session_id = orchestrator.initialize_run(
            profile="test-profile",
            providers={
                "planner": "generator-fn",
                "generator": "fake",
                "reviewer": "fake",
                "reviser": "fake",
            },
            context={"entity": "MyEntity"},
        )

        orchestrator.init(session_id)
        orchestrator.approve(session_id)

        response_path = (
            sessions_root
            / session_id
            / "iteration-1"
            / "planning-response.md"
        )
        content = response_path.read_text(encoding="utf-8")
        # Note: entity is passed in metadata, not top-level context
        assert "Custom response" in content


class TestFakeProviderArtifacts:
    """Tests for artifact creation with fake provider."""

    def test_generation_creates_artifacts(
        self,
        orchestrator: WorkflowOrchestrator,
        session_with_fake_provider: str,
        sessions_root: Path,
        mock_profile: MagicMock,
    ) -> None:
        """Generation phase creates code artifacts."""
        session_id = session_with_fake_provider

        # Run through to GENERATE[RESPONSE]
        orchestrator.init(session_id)
        orchestrator.approve(session_id)  # PLAN[PROMPT] -> PLAN[RESPONSE]
        orchestrator.approve(session_id)  # PLAN[RESPONSE] -> GENERATE[PROMPT]
        orchestrator.approve(session_id)  # GENERATE[PROMPT] -> GENERATE[RESPONSE]

        # Approve generation response (triggers code extraction)
        state = orchestrator.approve(session_id)

        # Should have artifacts
        assert len(state.artifacts) > 0

        # Verify artifact file exists
        artifact = state.artifacts[0]
        artifact_path = sessions_root / session_id / artifact.path
        assert artifact_path.exists()
"""Tests for run_provider() function in approval_handler."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from aiwf.application.approval_handler import run_provider
from aiwf.domain.errors import ProviderError
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.provider_factory import ProviderFactory


class MockProvider(AIProvider):
    """Mock provider that returns a configurable response."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.response = self.config.get("response", "mock response")
        self.should_fail = self.config.get("should_fail", False)
        self.validate_should_fail = self.config.get("validate_should_fail", False)

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "mock",
            "description": "Mock provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        if self.validate_should_fail:
            raise ProviderError("Mock validation failed")

    def generate(self, prompt: str, *args, **kwargs) -> str | None:
        if self.should_fail:
            raise ProviderError("Mock provider failed")
        return self.response


@pytest.fixture
def register_mock_provider():
    """Register mock provider for test, then clean up after."""
    ProviderFactory.register("mock", MockProvider)
    yield
    # Clean up - remove from registry
    if "mock" in ProviderFactory._registry:
        del ProviderFactory._registry["mock"]


def test_run_provider_invokes_factory_and_returns_response(register_mock_provider):
    """run_provider creates provider via factory and returns generate() result."""
    result = run_provider("mock", "test prompt")
    assert result == "mock response"


def test_run_provider_returns_none_for_manual():
    """run_provider returns None when ManualProvider returns None."""
    result = run_provider("manual", "test prompt")
    assert result is None


def test_handler_does_not_write_response_when_provider_returns_none(
    sessions_root: Path,
):
    """IngPhaseApprovalHandler skips file write when provider returns None.

    This locks in the contract that manual-mode providers (returning None)
    don't cause response files to be written - the user provides the response.
    """
    from aiwf.application.approval_handler import IngPhaseApprovalHandler
    from aiwf.domain.models.workflow_state import (
        ExecutionMode,
        WorkflowPhase,
        WorkflowState,
        WorkflowStatus,
    )

    # Create minimal session directory with prompt file
    session_dir = sessions_root / "test-session"
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True)

    prompt_file = iteration_dir / "planning-prompt.md"
    prompt_file.write_text("Test prompt content", encoding="utf-8")

    # Build state in PLANNING phase with manual provider
    state = WorkflowState(
        session_id="test-session",
        profile="jpa-mt",
        scope="domain",
        entity="TestEntity",
        providers={"planner": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=WorkflowPhase.PLANNING,
        status=WorkflowStatus.IN_PROGRESS,
        standards_hash="0" * 64,
        phase_history=[],
    )

    handler = IngPhaseApprovalHandler()
    handler.handle(session_dir=session_dir, state=state, hash_prompts=False)

    # Response file should NOT exist because manual provider returns None
    response_file = iteration_dir / "planning-response.md"
    assert not response_file.exists(), "Response file should not be written for manual provider"


def test_run_provider_raises_keyerror_for_unknown_provider():
    """run_provider raises KeyError for unregistered provider."""
    with pytest.raises(KeyError):
        run_provider("nonexistent-provider", "test prompt")


def test_run_provider_propagates_provider_error(register_mock_provider):
    """run_provider lets ProviderError propagate from generate()."""
    # Create a mock provider that fails
    class FailingProvider(MockProvider):
        def generate(self, prompt, *args, **kwargs):
            raise ProviderError("Provider generate failed")

    ProviderFactory.register("failing", FailingProvider)

    try:
        with pytest.raises(ProviderError, match="Provider generate failed"):
            run_provider("failing", "test prompt")
    finally:
        if "failing" in ProviderFactory._registry:
            del ProviderFactory._registry["failing"]


def test_run_provider_passes_timeouts_from_metadata(register_mock_provider):
    """run_provider reads timeout values from provider metadata and passes to generate()."""
    call_args = {}

    class TimeoutTrackingProvider(MockProvider):
        def generate(self, prompt, *args, connection_timeout=None, response_timeout=None, **kwargs):
            call_args["connection_timeout"] = connection_timeout
            call_args["response_timeout"] = response_timeout
            return "response"

        @classmethod
        def get_metadata(cls):
            return {
                "name": "timeout-tracker",
                "description": "Tracks timeout args",
                "requires_config": False,
                "config_keys": [],
                "default_connection_timeout": 15,
                "default_response_timeout": 120,
            }

    ProviderFactory.register("timeout-tracker", TimeoutTrackingProvider)

    try:
        run_provider("timeout-tracker", "test prompt")
        assert call_args["connection_timeout"] == 15
        assert call_args["response_timeout"] == 120
    finally:
        if "timeout-tracker" in ProviderFactory._registry:
            del ProviderFactory._registry["timeout-tracker"]
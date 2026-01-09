"""Tests for provider timeout override semantics.

These tests verify that timeout parameters are correctly passed and that
override behavior works as expected via ProviderExecutionService.
"""

from typing import Any

import pytest

from aiwf.application.providers import ProviderExecutionService
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.provider_factory import AIProviderFactory


class TimeoutTrackingProvider(AIProvider):
    """Provider that records timeout values passed to generate()."""

    # Class-level storage to track calls across instances
    last_call_timeouts: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "timeout-tracker",
            "description": "Tracks timeout parameters",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 15,
            "default_response_timeout": 120,
        }

    def validate(self) -> None:
        pass

    def generate(
        self,
        prompt: str,
        *args,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
        **kwargs,
    ) -> AIProviderResult | None:
        TimeoutTrackingProvider.last_call_timeouts = {
            "connection_timeout": connection_timeout,
            "response_timeout": response_timeout,
        }
        return AIProviderResult(response="response")


class NoneTimeoutProvider(AIProvider):
    """Provider with None timeout defaults (meaning no timeout)."""

    last_call_timeouts: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "none-timeout",
            "description": "Provider with None timeouts",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": None,
            "default_response_timeout": None,
        }

    def validate(self) -> None:
        pass

    def generate(
        self,
        prompt: str,
        *args,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
        **kwargs,
    ) -> AIProviderResult | None:
        NoneTimeoutProvider.last_call_timeouts = {
            "connection_timeout": connection_timeout,
            "response_timeout": response_timeout,
        }
        return AIProviderResult(response="response")


class ZeroTimeoutProvider(AIProvider):
    """Provider with zero timeout defaults (meaning no timeout per ADR-0007)."""

    last_call_timeouts: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "zero-timeout",
            "description": "Provider with zero timeouts",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 0,
            "default_response_timeout": 0,
        }

    def validate(self) -> None:
        pass

    def generate(
        self,
        prompt: str,
        *args,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
        **kwargs,
    ) -> AIProviderResult | None:
        ZeroTimeoutProvider.last_call_timeouts = {
            "connection_timeout": connection_timeout,
            "response_timeout": response_timeout,
        }
        return AIProviderResult(response="response")


@pytest.fixture
def register_timeout_providers():
    """Register timeout tracking providers and clean up after."""
    original_registry = dict(AIProviderFactory._registry)
    AIProviderFactory.register("timeout-tracker", TimeoutTrackingProvider)
    AIProviderFactory.register("none-timeout", NoneTimeoutProvider)
    AIProviderFactory.register("zero-timeout", ZeroTimeoutProvider)

    # Reset tracking state
    TimeoutTrackingProvider.last_call_timeouts = {}
    NoneTimeoutProvider.last_call_timeouts = {}
    ZeroTimeoutProvider.last_call_timeouts = {}

    yield

    AIProviderFactory._registry.clear()
    AIProviderFactory._registry.update(original_registry)


@pytest.fixture
def provider_service():
    """Create a ProviderExecutionService instance."""
    return ProviderExecutionService()


class TestTimeoutDefaults:
    """Tests for timeout default behavior from provider metadata."""

    def test_metadata_defaults_passed_to_generate(self, register_timeout_providers, provider_service):
        """ProviderExecutionService passes metadata default timeouts to generate()."""
        provider_service.execute_simple("timeout-tracker", "test prompt")

        assert TimeoutTrackingProvider.last_call_timeouts["connection_timeout"] == 15
        assert TimeoutTrackingProvider.last_call_timeouts["response_timeout"] == 120

    def test_none_timeout_defaults_passed_as_none(self, register_timeout_providers, provider_service):
        """Provider with None timeout defaults passes None to generate()."""
        provider_service.execute_simple("none-timeout", "test prompt")

        assert NoneTimeoutProvider.last_call_timeouts["connection_timeout"] is None
        assert NoneTimeoutProvider.last_call_timeouts["response_timeout"] is None

    def test_zero_timeout_defaults_passed_as_zero(self, register_timeout_providers, provider_service):
        """Provider with zero timeout defaults passes 0 to generate().

        Per ADR-0007, 0 means "no timeout" - the operation can take unlimited time.
        """
        provider_service.execute_simple("zero-timeout", "test prompt")

        assert ZeroTimeoutProvider.last_call_timeouts["connection_timeout"] == 0
        assert ZeroTimeoutProvider.last_call_timeouts["response_timeout"] == 0


class TestTimeoutSemantics:
    """Tests for timeout semantic meanings per ADR-0007."""

    def test_positive_timeout_is_enforced(self, register_timeout_providers, provider_service):
        """Positive timeout value should be passed through for enforcement."""
        # This test verifies the value is passed - actual enforcement is provider's job
        provider_service.execute_simple("timeout-tracker", "test prompt")

        conn = TimeoutTrackingProvider.last_call_timeouts["connection_timeout"]
        resp = TimeoutTrackingProvider.last_call_timeouts["response_timeout"]

        assert conn > 0, "Connection timeout should be positive"
        assert resp > 0, "Response timeout should be positive"

    def test_none_means_no_timeout_or_use_default(self, register_timeout_providers, provider_service):
        """None timeout means no timeout or use provider's internal default.

        Per ADR-0007: None = use default. When metadata specifies None,
        it means the provider has no default timeout.
        """
        provider_service.execute_simple("none-timeout", "test prompt")

        # None should be passed through
        assert NoneTimeoutProvider.last_call_timeouts["connection_timeout"] is None
        assert NoneTimeoutProvider.last_call_timeouts["response_timeout"] is None

    def test_zero_means_no_timeout(self, register_timeout_providers, provider_service):
        """Zero timeout means no timeout - operation can take unlimited time.

        Per ADR-0007: 0 = no timeout.
        """
        provider_service.execute_simple("zero-timeout", "test prompt")

        # 0 should be passed through (not converted to None)
        assert ZeroTimeoutProvider.last_call_timeouts["connection_timeout"] == 0
        assert ZeroTimeoutProvider.last_call_timeouts["response_timeout"] == 0


class TestProviderMetadataTimeouts:
    """Tests for various provider timeout metadata configurations."""

    def test_response_provider_default_metadata_has_timeouts(self):
        """AIProvider base class provides default timeout values."""
        metadata = AIProvider.get_metadata()

        assert "default_connection_timeout" in metadata
        assert "default_response_timeout" in metadata
        assert metadata["default_connection_timeout"] == 10
        assert metadata["default_response_timeout"] == 300  # 5 minutes

    def test_manual_provider_metadata_timeouts(self):
        """ManualAIProvider has appropriate timeout metadata."""
        from aiwf.domain.providers.manual_provider import ManualAIProvider

        metadata = ManualAIProvider.get_metadata()

        # Manual provider doesn't make network calls, but should still have metadata
        assert "default_connection_timeout" in metadata
        assert "default_response_timeout" in metadata
"""Unit tests for AIProviderFactory (response providers).

Mirrors test_standards_provider_factory.py structure for consistency.
"""

import pytest
from typing import Any

from aiwf.domain.providers.provider_factory import AIProviderFactory
from aiwf.domain.providers.ai_provider import AIProvider


class MockAIProvider(AIProvider):
    """Mock response provider for testing."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "mock-response-provider",
            "description": "Mock response provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        pass

    def generate(self, prompt: str, *args, **kwargs) -> str | None:
        return "mock response"


class TestAIProviderFactory:
    """Tests for AIProviderFactory."""

    def setup_method(self):
        """Save and clear the registry before each test."""
        self._original_registry = dict(AIProviderFactory._registry)
        AIProviderFactory._registry.clear()

    def teardown_method(self):
        """Restore the registry after each test."""
        AIProviderFactory._registry.clear()
        AIProviderFactory._registry.update(self._original_registry)

    def test_register_and_create(self):
        """Factory can register and create providers."""
        AIProviderFactory.register("mock", MockAIProvider)

        provider = AIProviderFactory.create("mock")

        assert isinstance(provider, MockAIProvider)
        assert provider.config == {}

    def test_create_with_config(self):
        """Factory passes config as kwargs to provider constructor."""
        AIProviderFactory.register("mock", MockAIProvider)
        # MockAIProvider accepts config dict in __init__
        config = {"config": {"api_key": "test-key"}}

        provider = AIProviderFactory.create("mock", config)

        assert provider.config == {"api_key": "test-key"}

    def test_create_unknown_raises_keyerror(self):
        """Creating unknown provider raises KeyError with helpful message."""
        with pytest.raises(KeyError) as exc_info:
            AIProviderFactory.create("unknown")

        assert "unknown" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_create_keyerror_lists_available_providers(self):
        """KeyError message lists available providers."""
        AIProviderFactory.register("mock1", MockAIProvider)
        AIProviderFactory.register("mock2", MockAIProvider)

        with pytest.raises(KeyError) as exc_info:
            AIProviderFactory.create("unknown")

        error_msg = str(exc_info.value)
        assert "mock1" in error_msg
        assert "mock2" in error_msg

    def test_list_providers_returns_registered_keys(self):
        """list_providers returns all registered keys."""
        AIProviderFactory.register("mock1", MockAIProvider)
        AIProviderFactory.register("mock2", MockAIProvider)

        keys = AIProviderFactory.list_providers()

        assert "mock1" in keys
        assert "mock2" in keys
        assert len(keys) == 2

    def test_list_providers_empty_when_no_registrations(self):
        """list_providers returns empty list when no providers registered."""
        keys = AIProviderFactory.list_providers()

        assert keys == []

    def test_is_registered_true_for_known_key(self):
        """is_registered returns True for registered provider key."""
        AIProviderFactory.register("mock", MockAIProvider)

        assert AIProviderFactory.is_registered("mock") is True

    def test_is_registered_false_for_unknown_key(self):
        """is_registered returns False for unregistered provider key."""
        assert AIProviderFactory.is_registered("unknown") is False

    def test_is_registered_false_when_empty_registry(self):
        """is_registered returns False when registry is empty."""
        assert AIProviderFactory.is_registered("any-key") is False

    def test_get_all_metadata_returns_metadata_list(self):
        """get_all_metadata returns list of metadata dicts."""
        AIProviderFactory.register("mock", MockAIProvider)

        all_metadata = AIProviderFactory.get_all_metadata()

        assert len(all_metadata) == 1
        assert all_metadata[0]["name"] == "mock-response-provider"
        assert all_metadata[0]["description"] == "Mock response provider for testing"

    def test_get_all_metadata_empty_when_no_registrations(self):
        """get_all_metadata returns empty list when no providers registered."""
        all_metadata = AIProviderFactory.get_all_metadata()

        assert all_metadata == []

    def test_get_metadata_returns_metadata_for_registered(self):
        """get_metadata returns metadata for registered provider."""
        AIProviderFactory.register("mock", MockAIProvider)

        metadata = AIProviderFactory.get_metadata("mock")

        assert metadata is not None
        assert metadata["name"] == "mock-response-provider"
        assert metadata["default_connection_timeout"] == 10
        assert metadata["default_response_timeout"] == 60

    def test_get_metadata_returns_none_for_unregistered(self):
        """get_metadata returns None for unregistered provider."""
        metadata = AIProviderFactory.get_metadata("unknown")

        assert metadata is None

    def test_register_overwrites_existing_registration(self):
        """Registering with same key overwrites previous registration."""

        class AnotherMockProvider(MockAIProvider):
            @classmethod
            def get_metadata(cls) -> dict[str, Any]:
                return {
                    "name": "another-mock",
                    "description": "Another mock",
                    "requires_config": True,
                    "config_keys": ["api_key"],
                    "default_connection_timeout": 15,
                    "default_response_timeout": 120,
                }

        AIProviderFactory.register("mock", MockAIProvider)
        AIProviderFactory.register("mock", AnotherMockProvider)

        metadata = AIProviderFactory.get_metadata("mock")
        assert metadata["name"] == "another-mock"

    def test_create_passes_kwargs_to_constructor(self):
        """Factory passes config as kwargs to constructor."""

        class ConfigurableProvider(AIProvider):
            def __init__(self, api_key: str = "", timeout: int = 30):
                self.api_key = api_key
                self.timeout = timeout

            @classmethod
            def get_metadata(cls) -> dict[str, Any]:
                return {
                    "name": "configurable",
                    "description": "Configurable provider",
                    "requires_config": True,
                    "config_keys": ["api_key", "timeout"],
                    "default_connection_timeout": 10,
                    "default_response_timeout": 60,
                }

            def validate(self) -> None:
                pass

            def generate(self, prompt: str, *args, **kwargs) -> str | None:
                return "response"

        AIProviderFactory.register("configurable", ConfigurableProvider)

        provider = AIProviderFactory.create(
            "configurable", {"api_key": "secret", "timeout": 60}
        )

        assert provider.api_key == "secret"
        assert provider.timeout == 60


class TestProviderMetadataContract:
    """Tests for provider metadata contract validation."""

    def setup_method(self):
        """Save and clear the registry before each test."""
        self._original_registry = dict(AIProviderFactory._registry)
        AIProviderFactory._registry.clear()

    def teardown_method(self):
        """Restore the registry after each test."""
        AIProviderFactory._registry.clear()
        AIProviderFactory._registry.update(self._original_registry)

    def test_metadata_has_required_keys(self):
        """Provider metadata contains all required keys."""
        AIProviderFactory.register("mock", MockAIProvider)

        metadata = AIProviderFactory.get_metadata("mock")

        required_keys = {
            "name",
            "description",
            "requires_config",
            "config_keys",
            "default_connection_timeout",
            "default_response_timeout",
        }
        assert required_keys.issubset(metadata.keys())

    def test_metadata_timeouts_are_int_or_none(self):
        """Provider metadata timeout values are int or None."""
        AIProviderFactory.register("mock", MockAIProvider)

        metadata = AIProviderFactory.get_metadata("mock")

        conn_timeout = metadata["default_connection_timeout"]
        resp_timeout = metadata["default_response_timeout"]

        assert conn_timeout is None or isinstance(conn_timeout, int)
        assert resp_timeout is None or isinstance(resp_timeout, int)

    def test_base_provider_has_sensible_defaults(self):
        """AIProvider base class provides sensible default metadata."""
        # Use base class default implementation
        metadata = AIProvider.get_metadata()

        assert metadata["name"] == "unknown"
        assert metadata["default_connection_timeout"] == 10
        assert metadata["default_response_timeout"] == 300
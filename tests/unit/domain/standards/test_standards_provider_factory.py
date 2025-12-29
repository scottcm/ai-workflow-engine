"""Unit tests for StandardsProviderFactory."""

import pytest
from typing import Any

from aiwf.domain.standards.standards_provider_factory import (
    StandardsProvider,
    StandardsProviderFactory,
)


class MockStandardsProvider:
    """Mock standards provider for testing."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "mock-provider",
            "description": "Mock standards provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 5,
            "default_response_timeout": 30,
        }

    def validate(self) -> None:
        pass

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        return "mock bundle"


class TestStandardsProviderFactory:
    """Tests for StandardsProviderFactory."""

    def setup_method(self):
        """Save and clear the registry before each test."""
        self._original_registry = dict(StandardsProviderFactory._registry)
        StandardsProviderFactory._registry.clear()

    def teardown_method(self):
        """Restore the registry after each test."""
        StandardsProviderFactory._registry.clear()
        StandardsProviderFactory._registry.update(self._original_registry)

    def test_register_and_create(self):
        """Factory can register and create providers."""
        StandardsProviderFactory.register("mock", MockStandardsProvider)

        provider = StandardsProviderFactory.create("mock")

        assert isinstance(provider, MockStandardsProvider)
        assert provider.config == {}

    def test_create_with_config(self):
        """Factory passes config to provider constructor."""
        StandardsProviderFactory.register("mock", MockStandardsProvider)
        config = {"key": "value"}

        provider = StandardsProviderFactory.create("mock", config)

        assert provider.config == config

    def test_create_unknown_raises_keyerror(self):
        """Creating unknown provider raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            StandardsProviderFactory.create("unknown")

        assert "unknown" in str(exc_info.value)
        assert "not registered" in str(exc_info.value)

    def test_list_providers_returns_registered_keys(self):
        """list_providers returns all registered keys."""
        StandardsProviderFactory.register("mock1", MockStandardsProvider)
        StandardsProviderFactory.register("mock2", MockStandardsProvider)

        keys = StandardsProviderFactory.list_providers()

        assert "mock1" in keys
        assert "mock2" in keys
        assert len(keys) == 2

    def test_list_providers_empty_when_no_registrations(self):
        """list_providers returns empty list when no providers registered."""
        keys = StandardsProviderFactory.list_providers()

        assert keys == []

    def test_is_registered_returns_true_for_registered(self):
        """is_registered returns True for registered providers."""
        StandardsProviderFactory.register("mock", MockStandardsProvider)

        assert StandardsProviderFactory.is_registered("mock") is True

    def test_is_registered_returns_false_for_unregistered(self):
        """is_registered returns False for unregistered providers."""
        assert StandardsProviderFactory.is_registered("unknown") is False

    def test_get_all_metadata_returns_metadata_list(self):
        """get_all_metadata returns list of metadata dicts."""
        StandardsProviderFactory.register("mock", MockStandardsProvider)

        all_metadata = StandardsProviderFactory.get_all_metadata()

        assert len(all_metadata) == 1
        assert all_metadata[0]["name"] == "mock-provider"
        assert all_metadata[0]["description"] == "Mock standards provider for testing"

    def test_get_metadata_returns_metadata_for_registered(self):
        """get_metadata returns metadata for registered provider."""
        StandardsProviderFactory.register("mock", MockStandardsProvider)

        metadata = StandardsProviderFactory.get_metadata("mock")

        assert metadata is not None
        assert metadata["name"] == "mock-provider"

    def test_get_metadata_returns_none_for_unregistered(self):
        """get_metadata returns None for unregistered provider."""
        metadata = StandardsProviderFactory.get_metadata("unknown")

        assert metadata is None

    def test_register_overwrites_existing_registration(self):
        """Registering with same key overwrites previous registration."""

        class AnotherMockProvider(MockStandardsProvider):
            @classmethod
            def get_metadata(cls) -> dict[str, Any]:
                return {
                    "name": "another-mock",
                    "description": "Another mock",
                    "requires_config": False,
                    "config_keys": [],
                    "default_connection_timeout": 10,
                    "default_response_timeout": 60,
                }

        StandardsProviderFactory.register("mock", MockStandardsProvider)
        StandardsProviderFactory.register("mock", AnotherMockProvider)

        metadata = StandardsProviderFactory.get_metadata("mock")
        assert metadata["name"] == "another-mock"
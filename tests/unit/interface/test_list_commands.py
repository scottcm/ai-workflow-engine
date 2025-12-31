"""Unit tests for CLI list commands (profiles, providers).

Tests for:
- aiwf profiles (list all profiles)
- aiwf profiles <name> (show profile details)
- aiwf providers (list all AI providers)
- aiwf providers <name> (show provider details)
"""

import json
import pytest
from click.testing import CliRunner
from typing import Any
from unittest.mock import patch, MagicMock

from aiwf.interface.cli.cli import cli
from aiwf.domain.providers.provider_factory import ProviderFactory
from aiwf.domain.providers.response_provider import ResponseProvider


class MockTestProvider(ResponseProvider):
    """Test provider for list command tests."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "test-provider",
            "description": "Test provider for CLI tests",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        pass

    def generate(self, prompt: str, *args, **kwargs) -> str | None:
        return "test response"


class TestProfilesCommand:
    """Tests for the profiles CLI command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_profile_metadata(self):
        """Mock profile metadata for tests."""
        return {
            "name": "jpa-mt",
            "description": "JPA Multi-Tier profile",
            "target_stack": "Java/Spring Boot",
            "scopes": ["domain", "application", "infrastructure"],
            "phases": ["PLAN", "GENERATE", "REVIEW", "REVISE"],
            "requires_config": True,
            "config_keys": ["standards.root"],
        }

    def test_profiles_lists_registered_profiles(self, runner):
        """profiles command lists all registered profiles."""
        result = runner.invoke(cli, ["profiles"])

        # jpa-mt is registered by default when profiles package is imported
        assert result.exit_code == 0
        assert "jpa-mt" in result.output

    def test_profiles_json_output(self, runner):
        """--json flag produces valid JSON output."""
        result = runner.invoke(cli, ["--json", "profiles"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["exit_code"] == 0
        assert "profiles" in output
        assert isinstance(output["profiles"], list)

    def test_profiles_json_contains_metadata(self, runner):
        """JSON output contains profile metadata fields."""
        result = runner.invoke(cli, ["--json", "profiles"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        # Verify top-level schema
        assert "exit_code" in output
        assert "command" in output
        assert output["command"] == "profiles"
        # Verify profile entries have required fields
        if output["profiles"]:
            profile = output["profiles"][0]
            required_fields = {"name", "description", "scopes"}
            assert required_fields.issubset(profile.keys()), (
                f"Profile missing required fields: {required_fields - set(profile.keys())}"
            )

    def test_profiles_detail_view(self, runner, mock_profile_metadata):
        """profiles <name> shows detailed profile information."""
        with patch(
            "aiwf.domain.profiles.profile_factory.ProfileFactory.get_metadata",
            return_value=mock_profile_metadata,
        ):
            result = runner.invoke(cli, ["profiles", "jpa-mt"])

        assert result.exit_code == 0
        assert "jpa-mt" in result.output
        assert "JPA Multi-Tier" in result.output

    def test_profiles_detail_json_output(self, runner, mock_profile_metadata):
        """profiles <name> --json shows detailed profile in JSON."""
        with patch(
            "aiwf.domain.profiles.profile_factory.ProfileFactory.get_metadata",
            return_value=mock_profile_metadata,
        ):
            result = runner.invoke(cli, ["--json", "profiles", "jpa-mt"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["exit_code"] == 0
        assert output["profile"]["name"] == "jpa-mt"
        assert output["profile"]["description"] == "JPA Multi-Tier profile"

    def test_profiles_unknown_profile_fails(self, runner):
        """profiles <unknown> fails with helpful error."""
        result = runner.invoke(cli, ["profiles", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_profiles_unknown_profile_json_error(self, runner):
        """profiles <unknown> --json returns error in JSON."""
        result = runner.invoke(cli, ["--json", "profiles", "nonexistent"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["exit_code"] == 1
        assert output["error"] is not None
        assert "not found" in output["error"].lower()


class TestProvidersCommand:
    """Tests for the providers CLI command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def register_test_provider(self):
        """Register test provider and clean up after."""
        original_registry = dict(ProviderFactory._registry)
        ProviderFactory.register("test-provider", MockTestProvider)
        yield
        ProviderFactory._registry.clear()
        ProviderFactory._registry.update(original_registry)

    def test_providers_lists_registered_providers(self, runner):
        """providers command lists registered providers."""
        result = runner.invoke(cli, ["providers"])

        assert result.exit_code == 0
        # manual provider should always be registered
        assert "manual" in result.output

    def test_providers_json_output(self, runner):
        """--json flag produces valid JSON output."""
        result = runner.invoke(cli, ["--json", "providers"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["exit_code"] == 0
        assert "providers" in output
        assert isinstance(output["providers"], list)

    def test_providers_json_contains_metadata(self, runner):
        """JSON output contains provider metadata fields."""
        result = runner.invoke(cli, ["--json", "providers"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        # Verify top-level schema
        assert "exit_code" in output
        assert "command" in output
        assert output["command"] == "providers"
        # Verify provider entries have required fields
        if output["providers"]:
            provider = output["providers"][0]
            required_fields = {"name", "description", "requires_config"}
            assert required_fields.issubset(provider.keys()), (
                f"Provider missing required fields: {required_fields - set(provider.keys())}"
            )

    def test_providers_detail_view(self, runner, register_test_provider):
        """providers <name> shows detailed provider information."""
        result = runner.invoke(cli, ["providers", "test-provider"])

        assert result.exit_code == 0
        assert "test-provider" in result.output
        assert "Test provider for CLI tests" in result.output

    def test_providers_detail_json_output(self, runner, register_test_provider):
        """providers <name> --json shows detailed provider in JSON."""
        result = runner.invoke(cli, ["--json", "providers", "test-provider"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["exit_code"] == 0
        assert output["provider"]["name"] == "test-provider"
        assert output["provider"]["description"] == "Test provider for CLI tests"

    def test_providers_unknown_provider_fails(self, runner):
        """providers <unknown> fails with helpful error."""
        result = runner.invoke(cli, ["providers", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_providers_unknown_provider_json_error(self, runner):
        """providers <unknown> --json returns error in JSON."""
        result = runner.invoke(cli, ["--json", "providers", "nonexistent"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["exit_code"] == 1
        assert output["error"] is not None
        assert "not found" in output["error"].lower()

    def test_providers_empty_shows_message(self, runner):
        """providers with no registrations shows appropriate message."""
        # Save and clear registry
        original_registry = dict(ProviderFactory._registry)
        ProviderFactory._registry.clear()

        try:
            result = runner.invoke(cli, ["providers"])

            assert result.exit_code == 0
            assert "no providers registered" in result.output.lower()
        finally:
            ProviderFactory._registry.clear()
            ProviderFactory._registry.update(original_registry)

    def test_providers_empty_json_returns_empty_list(self, runner):
        """providers --json with no registrations returns empty list."""
        # Save and clear registry
        original_registry = dict(ProviderFactory._registry)
        ProviderFactory._registry.clear()

        try:
            result = runner.invoke(cli, ["--json", "providers"])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["providers"] == []
        finally:
            ProviderFactory._registry.clear()
            ProviderFactory._registry.update(original_registry)


class TestProvidersCommandWithManual:
    """Tests for providers command with manual provider."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_manual_provider_in_list(self, runner):
        """Manual provider appears in providers list."""
        result = runner.invoke(cli, ["providers"])

        assert result.exit_code == 0
        assert "manual" in result.output

    def test_manual_provider_detail(self, runner):
        """Manual provider details are accessible."""
        result = runner.invoke(cli, ["providers", "manual"])

        assert result.exit_code == 0
        assert "manual" in result.output

    def test_manual_provider_detail_json(self, runner):
        """Manual provider JSON details include expected fields."""
        result = runner.invoke(cli, ["--json", "providers", "manual"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["provider"]["name"] == "manual"
        assert output["provider"]["requires_config"] is False
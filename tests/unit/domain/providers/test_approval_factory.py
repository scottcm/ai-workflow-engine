"""Tests for ApprovalProviderFactory.

TDD Tests for ADR-0012 Phase 4.
"""

from unittest.mock import Mock, patch

import pytest

from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.approval_factory import ApprovalProviderFactory
from aiwf.domain.providers.skip_approver import SkipApprovalProvider
from aiwf.domain.providers.manual_approver import ManualApprovalProvider
from aiwf.domain.providers.ai_approver import AIApprovalProvider


class TestApprovalProviderFactoryBuiltins:
    """Tests for built-in provider creation."""

    def test_create_skip_provider(self) -> None:
        """Factory creates SkipApprovalProvider for 'skip' key."""
        provider = ApprovalProviderFactory.create("skip")
        assert isinstance(provider, SkipApprovalProvider)

    def test_create_manual_provider(self) -> None:
        """Factory creates ManualApprovalProvider for 'manual' key."""
        provider = ApprovalProviderFactory.create("manual")
        assert isinstance(provider, ManualApprovalProvider)

    def test_builtin_providers_are_approval_providers(self) -> None:
        """All built-in providers implement ApprovalProvider."""
        skip = ApprovalProviderFactory.create("skip")
        manual = ApprovalProviderFactory.create("manual")

        assert isinstance(skip, ApprovalProvider)
        assert isinstance(manual, ApprovalProvider)


class TestApprovalProviderFactoryAIFallback:
    """Tests for AI provider fallback behavior."""

    def test_unknown_key_creates_ai_approval_provider(self) -> None:
        """Unknown key creates AIApprovalProvider wrapping AI provider."""
        mock_ai = Mock(spec=AIProvider)

        with patch(
            "aiwf.domain.providers.approval_factory.ProviderFactory"
        ) as mock_factory:
            mock_factory.create.return_value = mock_ai

            provider = ApprovalProviderFactory.create("claude")

            assert isinstance(provider, AIApprovalProvider)
            mock_factory.create.assert_called_once_with("claude", None)

    def test_ai_fallback_passes_config_to_provider_factory(self) -> None:
        """AI fallback passes config to ProviderFactory.create."""
        mock_ai = Mock(spec=AIProvider)
        config = {"api_key": "test-key", "model": "claude-3"}

        with patch(
            "aiwf.domain.providers.approval_factory.ProviderFactory"
        ) as mock_factory:
            mock_factory.create.return_value = mock_ai

            ApprovalProviderFactory.create("claude", config=config)

            mock_factory.create.assert_called_once_with("claude", config)

    def test_ai_fallback_propagates_provider_factory_errors(self) -> None:
        """If ProviderFactory.create fails, error propagates."""
        with patch(
            "aiwf.domain.providers.approval_factory.ProviderFactory"
        ) as mock_factory:
            mock_factory.create.side_effect = KeyError("Provider 'unknown' not found")

            with pytest.raises(KeyError):
                ApprovalProviderFactory.create("unknown")


class TestApprovalProviderFactoryRegistration:
    """Tests for custom provider registration."""

    def test_register_custom_provider(self) -> None:
        """Can register custom approval provider."""

        class CustomApprover(ApprovalProvider):
            def evaluate(self, **kwargs):
                pass

            @property
            def requires_user_input(self) -> bool:
                return False

        ApprovalProviderFactory.register("custom", CustomApprover)

        provider = ApprovalProviderFactory.create("custom")
        assert isinstance(provider, CustomApprover)

        # Cleanup: remove custom provider to not affect other tests
        ApprovalProviderFactory._registry.pop("custom", None)

    def test_register_overwrites_existing(self) -> None:
        """Registering same key overwrites previous provider."""

        class CustomSkip(ApprovalProvider):
            def evaluate(self, **kwargs):
                pass

            @property
            def requires_user_input(self) -> bool:
                return False

        # Save original
        original = ApprovalProviderFactory._registry.get("skip")

        try:
            ApprovalProviderFactory.register("skip", CustomSkip)
            provider = ApprovalProviderFactory.create("skip")
            assert isinstance(provider, CustomSkip)
        finally:
            # Restore original
            if original:
                ApprovalProviderFactory._registry["skip"] = original


class TestApprovalProviderFactoryListing:
    """Tests for provider listing."""

    def test_list_providers_includes_builtins(self) -> None:
        """list_providers includes built-in providers."""
        providers = ApprovalProviderFactory.list_providers()

        assert "skip" in providers
        assert "manual" in providers

    def test_list_providers_returns_list(self) -> None:
        """list_providers returns a list of strings."""
        providers = ApprovalProviderFactory.list_providers()

        assert isinstance(providers, list)
        assert all(isinstance(p, str) for p in providers)


class TestApprovalProviderFactoryConfig:
    """Tests for config handling."""

    def test_builtin_providers_ignore_config(self) -> None:
        """Built-in providers (skip, manual) ignore config parameter."""
        # Should not raise even with config
        skip = ApprovalProviderFactory.create("skip", config={"ignored": "value"})
        manual = ApprovalProviderFactory.create("manual", config={"also": "ignored"})

        assert isinstance(skip, SkipApprovalProvider)
        assert isinstance(manual, ManualApprovalProvider)

    def test_ai_provider_receives_config(self) -> None:
        """AI provider creation receives config."""
        mock_ai = Mock(spec=AIProvider)
        config = {"model": "gpt-4", "temperature": 0.7}

        with patch(
            "aiwf.domain.providers.approval_factory.ProviderFactory"
        ) as mock_factory:
            mock_factory.create.return_value = mock_ai

            ApprovalProviderFactory.create("gpt", config=config)

            mock_factory.create.assert_called_once_with("gpt", config)
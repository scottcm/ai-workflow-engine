"""Tests for AI provider capability metadata."""

import pytest
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.manual_provider import ManualAIProvider


class TestProviderCapabilityMetadata:
    """Tests for provider capability metadata fields."""

    def test_default_metadata_includes_fs_ability(self):
        """Base AIProvider metadata includes fs_ability field."""
        metadata = AIProvider.get_metadata()
        assert "fs_ability" in metadata
        assert metadata["fs_ability"] == "local-write"  # Default: assume best case

    def test_default_metadata_includes_supports_system_prompt(self):
        """Base AIProvider metadata includes supports_system_prompt field."""
        metadata = AIProvider.get_metadata()
        assert "supports_system_prompt" in metadata
        assert metadata["supports_system_prompt"] is False

    def test_default_metadata_includes_supports_file_attachments(self):
        """Base AIProvider metadata includes supports_file_attachments field."""
        metadata = AIProvider.get_metadata()
        assert "supports_file_attachments" in metadata
        assert metadata["supports_file_attachments"] is False

    def test_capability_fields_have_correct_types(self):
        """Capability fields have expected types."""
        metadata = AIProvider.get_metadata()

        # fs_ability is string or None
        assert metadata["fs_ability"] is None or isinstance(metadata["fs_ability"], str)
        # Boolean fields
        assert isinstance(metadata["supports_system_prompt"], bool)
        assert isinstance(metadata["supports_file_attachments"], bool)


class TestManualAIProviderMetadata:
    """Tests for ManualAIProvider capability metadata."""

    def test_manual_provider_fs_ability_is_none(self):
        """ManualAIProvider has fs_ability=None since it depends on where user pastes."""
        metadata = ManualAIProvider.get_metadata()
        assert metadata["fs_ability"] is None

    def test_manual_provider_no_system_prompt_support(self):
        """ManualAIProvider doesn't inherently support system prompts."""
        metadata = ManualAIProvider.get_metadata()
        assert metadata["supports_system_prompt"] is False

    def test_manual_provider_no_file_attachment_support(self):
        """ManualAIProvider doesn't inherently support file attachments."""
        metadata = ManualAIProvider.get_metadata()
        assert metadata["supports_file_attachments"] is False


class TestAIProviderImports:
    """Tests for AIProvider imports from package."""

    def test_aiprovider_importable_from_package(self):
        """AIProvider is importable from package."""
        from aiwf.domain.providers import AIProvider as PackageAIProvider
        from aiwf.domain.providers.ai_provider import AIProvider as DirectAIProvider
        assert PackageAIProvider is DirectAIProvider
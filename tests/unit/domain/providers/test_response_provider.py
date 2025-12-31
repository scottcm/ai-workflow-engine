"""Tests for response provider capability metadata."""

import pytest
from aiwf.domain.providers.response_provider import ResponseProvider
from aiwf.domain.providers.manual_provider import ManualProvider


class TestProviderCapabilityMetadata:
    """Tests for provider capability metadata fields."""

    def test_default_metadata_includes_fs_ability(self):
        """Base ResponseProvider metadata includes fs_ability field."""
        metadata = ResponseProvider.get_metadata()
        assert "fs_ability" in metadata
        assert metadata["fs_ability"] == "local-write"  # Default: assume best case

    def test_default_metadata_includes_supports_system_prompt(self):
        """Base ResponseProvider metadata includes supports_system_prompt field."""
        metadata = ResponseProvider.get_metadata()
        assert "supports_system_prompt" in metadata
        assert metadata["supports_system_prompt"] is False

    def test_default_metadata_includes_supports_file_attachments(self):
        """Base ResponseProvider metadata includes supports_file_attachments field."""
        metadata = ResponseProvider.get_metadata()
        assert "supports_file_attachments" in metadata
        assert metadata["supports_file_attachments"] is False

    def test_capability_fields_have_correct_types(self):
        """Capability fields have expected types."""
        metadata = ResponseProvider.get_metadata()

        # fs_ability is string or None
        assert metadata["fs_ability"] is None or isinstance(metadata["fs_ability"], str)
        # Boolean fields
        assert isinstance(metadata["supports_system_prompt"], bool)
        assert isinstance(metadata["supports_file_attachments"], bool)


class TestManualProviderMetadata:
    """Tests for ManualProvider capability metadata."""

    def test_manual_provider_fs_ability_is_none(self):
        """ManualProvider has fs_ability=None since it depends on where user pastes."""
        metadata = ManualProvider.get_metadata()
        assert metadata["fs_ability"] is None

    def test_manual_provider_no_system_prompt_support(self):
        """ManualProvider doesn't inherently support system prompts."""
        metadata = ManualProvider.get_metadata()
        assert metadata["supports_system_prompt"] is False

    def test_manual_provider_no_file_attachment_support(self):
        """ManualProvider doesn't inherently support file attachments."""
        metadata = ManualProvider.get_metadata()
        assert metadata["supports_file_attachments"] is False


class TestAIProviderBackwardsCompatibility:
    """Tests for AIProvider backwards compatibility alias."""

    def test_aiprovider_alias_is_response_provider(self):
        """AIProvider alias points to ResponseProvider."""
        from aiwf.domain.providers.response_provider import AIProvider
        assert AIProvider is ResponseProvider

    def test_aiprovider_importable_from_package(self):
        """AIProvider is importable from package for backwards compatibility."""
        from aiwf.domain.providers import AIProvider
        assert AIProvider is ResponseProvider
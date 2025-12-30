"""Tests for fs_ability resolution with precedence rules."""

import pytest
from aiwf.application.config_loader import resolve_fs_ability


class TestResolveFsAbility:
    """Tests for resolve_fs_ability() precedence: CLI > config > provider > default."""

    # --- CLI Override (Highest Precedence) ---

    def test_cli_override_takes_precedence_over_all(self):
        """CLI --fs-ability overrides everything else."""
        result = resolve_fs_ability(
            cli_override="none",
            provider_key="claude-code",
            config={
                "providers": {
                    "defaults": {"fs_ability": "write-only"},
                    "claude-code": {"fs_ability": "local-read"},
                }
            },
            provider_metadata={"fs_ability": "local-write"},
        )
        assert result == "none"

    def test_cli_override_with_empty_config(self):
        """CLI override works with empty config."""
        result = resolve_fs_ability(
            cli_override="local-read",
            provider_key="manual",
            config={},
            provider_metadata={"fs_ability": None},
        )
        assert result == "local-read"

    # --- Per-Provider Config (Second Precedence) ---

    def test_per_provider_config_overrides_defaults_and_metadata(self):
        """Per-provider config overrides global defaults and provider metadata."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={
                "providers": {
                    "defaults": {"fs_ability": "local-write"},
                    "manual": {"fs_ability": "write-only"},
                }
            },
            provider_metadata={"fs_ability": None},
        )
        assert result == "write-only"

    def test_per_provider_config_without_global_defaults(self):
        """Per-provider config works without global defaults section."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="claude-code",
            config={
                "providers": {
                    "claude-code": {"fs_ability": "local-write"},
                }
            },
            provider_metadata={"fs_ability": "local-read"},
        )
        assert result == "local-write"

    # --- Global Default Config (Third Precedence) ---

    def test_global_default_overrides_provider_metadata(self):
        """Global default config overrides provider metadata."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="some-provider",
            config={
                "providers": {
                    "defaults": {"fs_ability": "none"},
                }
            },
            provider_metadata={"fs_ability": "local-write"},
        )
        assert result == "none"

    def test_global_default_used_when_no_per_provider_config(self):
        """Global default used when provider has no specific config."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="unknown-provider",
            config={
                "providers": {
                    "defaults": {"fs_ability": "write-only"},
                    "other-provider": {"fs_ability": "local-write"},
                }
            },
            provider_metadata={"fs_ability": None},
        )
        assert result == "write-only"

    # --- Provider Metadata (Fourth Precedence) ---

    def test_provider_metadata_used_when_no_config(self):
        """Provider metadata used when no CLI or config override."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="claude-code",
            config={},
            provider_metadata={"fs_ability": "local-write"},
        )
        assert result == "local-write"

    def test_provider_metadata_used_with_empty_providers_section(self):
        """Provider metadata used when providers section is empty."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="claude-code",
            config={"providers": {}},
            provider_metadata={"fs_ability": "local-read"},
        )
        assert result == "local-read"

    # --- Engine Default (Lowest Precedence) ---

    def test_engine_default_when_all_sources_empty(self):
        """Falls back to engine default 'local-write' when all sources empty."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={},
            provider_metadata={},
        )
        assert result == "local-write"

    def test_engine_default_when_provider_metadata_is_none(self):
        """Falls back to engine default when provider metadata fs_ability is None."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={},
            provider_metadata={"fs_ability": None},
        )
        assert result == "local-write"

    def test_engine_default_when_provider_metadata_missing_key(self):
        """Falls back to engine default when provider metadata lacks fs_ability key."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={},
            provider_metadata={"name": "manual"},  # No fs_ability key
        )
        assert result == "local-write"

    # --- Precedence Order Verification ---

    def test_full_precedence_chain(self):
        """Verify complete precedence chain with all sources populated."""
        # Use valid fs_ability values at each level
        config = {
            "providers": {
                "defaults": {"fs_ability": "write-only"},      # Level 3
                "test-provider": {"fs_ability": "local-read"}, # Level 2
            }
        }
        provider_metadata = {"fs_ability": "local-write"}      # Level 4

        # CLI wins (level 1)
        assert resolve_fs_ability("none", "test-provider", config, provider_metadata) == "none"

        # Per-provider config wins (no CLI) - level 2
        assert resolve_fs_ability(None, "test-provider", config, provider_metadata) == "local-read"

        # Global default wins (no CLI, no per-provider) - level 3
        config_no_provider = {"providers": {"defaults": {"fs_ability": "write-only"}}}
        assert resolve_fs_ability(None, "other-provider", config_no_provider, provider_metadata) == "write-only"

        # Provider metadata wins (no CLI, no config) - level 4
        assert resolve_fs_ability(None, "test-provider", {}, provider_metadata) == "local-write"

        # Engine default (nothing else) - level 5
        assert resolve_fs_ability(None, "test-provider", {}, {}) == "local-write"


class TestFsAbilityConfigValidation:
    """Tests for invalid fs_ability values in config raising ConfigLoadError."""

    def test_invalid_per_provider_fs_ability_raises_error(self):
        """Invalid fs_ability in per-provider config raises ConfigLoadError."""
        from aiwf.application.config_loader import ConfigLoadError

        with pytest.raises(ConfigLoadError) as exc_info:
            resolve_fs_ability(
                cli_override=None,
                provider_key="manual",
                config={
                    "providers": {
                        "manual": {"fs_ability": "local-rad"},  # Typo
                    }
                },
                provider_metadata={},
            )
        assert "Invalid fs_ability 'local-rad'" in str(exc_info.value)
        assert "providers.manual.fs_ability" in str(exc_info.value)

    def test_invalid_global_default_fs_ability_raises_error(self):
        """Invalid fs_ability in global defaults raises ConfigLoadError."""
        from aiwf.application.config_loader import ConfigLoadError

        with pytest.raises(ConfigLoadError) as exc_info:
            resolve_fs_ability(
                cli_override=None,
                provider_key="some-provider",
                config={
                    "providers": {
                        "defaults": {"fs_ability": "invalid-value"},
                    }
                },
                provider_metadata={},
            )
        assert "Invalid fs_ability 'invalid-value'" in str(exc_info.value)
        assert "providers.defaults.fs_ability" in str(exc_info.value)

    def test_error_message_includes_valid_values(self):
        """Error message lists valid fs_ability values."""
        from aiwf.application.config_loader import ConfigLoadError

        with pytest.raises(ConfigLoadError) as exc_info:
            resolve_fs_ability(
                cli_override=None,
                provider_key="manual",
                config={
                    "providers": {
                        "manual": {"fs_ability": "bad"},
                    }
                },
                provider_metadata={},
            )
        error_msg = str(exc_info.value)
        assert "local-write" in error_msg
        assert "local-read" in error_msg
        assert "write-only" in error_msg
        assert "none" in error_msg
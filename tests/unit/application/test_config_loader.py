"""Tests for config loading and fs_ability resolution.

Includes:
- fs_ability resolution with precedence rules
- V2 workflow config loading (load_workflow_config)
- Provider key validation (validate_provider_keys)
"""

from pathlib import Path
import pytest
from aiwf.application.config_loader import (
    resolve_fs_ability,
    load_workflow_config,
    validate_provider_keys,
    ConfigLoadError,
)
from aiwf.application.config_models import (
    StageConfig,
    PhaseConfig,
    WorkflowConfig,
)
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


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


class TestLoadWorkflowConfig:
    """Tests for load_workflow_config() V2 workflow config loading."""

    def test_load_valid_yaml(self, tmp_path: Path):
        """Parses valid YAML workflow config without error."""
        config_content = """
workflow:
  defaults:
    ai_provider: claude-code
    approval_provider: manual
  plan:
    prompt:
      approval_provider: skip
    response:
      approval_provider: claude-code
"""
        config_file = tmp_path / "workflow.yml"
        config_file.write_text(config_content)

        config = load_workflow_config(config_file)

        assert config.defaults.ai_provider == "claude-code"
        assert config.defaults.approval_provider == "manual"
        assert config.plan is not None
        assert config.plan.prompt.approval_provider == "skip"
        assert config.plan.response.approval_provider == "claude-code"

    def test_load_minimal_config(self, tmp_path: Path):
        """Parses minimal config with just defaults."""
        config_content = """
workflow:
  defaults:
    ai_provider: claude-code
"""
        config_file = tmp_path / "workflow.yml"
        config_file.write_text(config_content)

        config = load_workflow_config(config_file)

        assert config.defaults.ai_provider == "claude-code"
        assert config.defaults.approval_provider == "manual"  # default value
        assert config.plan is None

    def test_load_full_config(self, tmp_path: Path):
        """Parses full config with all phases and stages."""
        config_content = """
workflow:
  defaults:
    ai_provider: claude-code
    approval_provider: manual
    approval_max_retries: 0
    approval_allow_rewrite: false

  plan:
    prompt:
      approval_provider: skip
    response:
      ai_provider: claude-code
      approval_provider: claude-code
      approval_max_retries: 2
      approver_config:
        model: "claude-3"

  generate:
    prompt:
      approval_provider: manual
    response:
      ai_provider: claude-code
      approval_provider: manual

  review:
    response:
      approval_allow_rewrite: true

  revise:
    prompt:
      approval_provider: skip
"""
        config_file = tmp_path / "workflow.yml"
        config_file.write_text(config_content)

        config = load_workflow_config(config_file)

        # Check defaults
        assert config.defaults.ai_provider == "claude-code"
        assert config.defaults.approval_max_retries == 0

        # Check plan phase
        assert config.plan.prompt.approval_provider == "skip"
        assert config.plan.response.approval_max_retries == 2
        assert config.plan.response.approver_config == {"model": "claude-3"}

        # Check generate phase
        assert config.generate.prompt.approval_provider == "manual"

        # Check review phase
        assert config.review.response.approval_allow_rewrite is True

        # Check revise phase
        assert config.revise.prompt.approval_provider == "skip"

    def test_load_missing_file_raises_error(self, tmp_path: Path):
        """Raises ConfigLoadError for missing file."""
        config_file = tmp_path / "nonexistent.yml"

        with pytest.raises(ConfigLoadError) as exc_info:
            load_workflow_config(config_file)

        assert "not found" in str(exc_info.value).lower()

    def test_load_malformed_yaml_raises_error(self, tmp_path: Path):
        """Raises ConfigLoadError for malformed YAML."""
        config_file = tmp_path / "bad.yml"
        config_file.write_text("workflow: {invalid: yaml: syntax")

        with pytest.raises(ConfigLoadError) as exc_info:
            load_workflow_config(config_file)

        assert "yaml" in str(exc_info.value).lower() or "Malformed" in str(exc_info.value)

    def test_load_missing_workflow_key_raises_error(self, tmp_path: Path):
        """Raises ConfigLoadError when 'workflow' key is missing."""
        config_file = tmp_path / "no-workflow.yml"
        config_file.write_text("defaults:\n  ai_provider: claude-code")

        with pytest.raises(ConfigLoadError) as exc_info:
            load_workflow_config(config_file)

        assert "workflow" in str(exc_info.value).lower()

    def test_load_unknown_phase_raises_error(self, tmp_path: Path):
        """Raises ConfigLoadError for unknown phase names."""
        config_content = """
workflow:
  defaults:
    ai_provider: claude-code
  unknown_phase:
    response:
      approval_provider: skip
"""
        config_file = tmp_path / "bad-phase.yml"
        config_file.write_text(config_content)

        with pytest.raises(ConfigLoadError) as exc_info:
            load_workflow_config(config_file)

        assert "unknown_phase" in str(exc_info.value)

    def test_load_unknown_stage_raises_error(self, tmp_path: Path):
        """Raises ConfigLoadError for unknown stage names."""
        config_content = """
workflow:
  defaults:
    ai_provider: claude-code
  plan:
    unknown_stage:
      approval_provider: skip
"""
        config_file = tmp_path / "bad-stage.yml"
        config_file.write_text(config_content)

        with pytest.raises(ConfigLoadError) as exc_info:
            load_workflow_config(config_file)

        assert "unknown_stage" in str(exc_info.value)


class TestValidateProviderKeys:
    """Tests for validate_provider_keys() dry-run validation."""

    def test_validate_known_ai_provider(self):
        """Passes validation for known AI provider keys."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="manual")
        )
        # Should not raise - "manual" is a registered AI provider
        validate_provider_keys(config)

    def test_validate_unknown_ai_provider(self):
        """Fails with clear message for unknown AI provider."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="unknown-provider")
        )
        with pytest.raises(ConfigLoadError) as exc_info:
            validate_provider_keys(config)

        assert "unknown-provider" in str(exc_info.value)
        assert "ai_provider" in str(exc_info.value).lower()

    def test_validate_known_approval_provider(self):
        """Passes validation for built-in approval provider keys."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="manual",
                approval_provider="skip",
            )
        )
        # Should not raise - "skip" is a built-in approval provider
        validate_provider_keys(config)

    def test_validate_ai_provider_as_approval(self):
        """Passes validation when AI provider used as approval (wrapping path)."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="manual",
                approval_provider="manual",  # AI provider used as approver
            )
        )
        # Should not raise - "manual" is a valid AI provider for wrapping
        # Note: manual can be used as approval provider via wrapping
        validate_provider_keys(config)

    def test_validate_unknown_approval_provider(self):
        """Fails with clear message for unknown approval provider."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="manual",
                approval_provider="unknown-approver",
            )
        )
        with pytest.raises(ConfigLoadError) as exc_info:
            validate_provider_keys(config)

        assert "unknown-approver" in str(exc_info.value)
        assert "approval" in str(exc_info.value).lower()

    def test_validate_all_stages(self):
        """Iterates all phase/stage combinations for validation."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="manual"),
            plan=PhaseConfig(
                prompt=StageConfig(approval_provider="skip"),
                response=StageConfig(
                    ai_provider="manual",
                    approval_provider="manual",
                ),
            ),
            generate=PhaseConfig(
                response=StageConfig(ai_provider="manual"),
            ),
        )
        # Should not raise - all keys are valid
        validate_provider_keys(config)

    def test_validate_detects_error_in_nested_stage(self):
        """Detects unknown provider key in deeply nested stage config."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="manual"),
            plan=PhaseConfig(
                response=StageConfig(
                    ai_provider="manual",
                    approval_provider="invalid-nested",
                ),
            ),
        )
        with pytest.raises(ConfigLoadError) as exc_info:
            validate_provider_keys(config)

        assert "invalid-nested" in str(exc_info.value)

    def test_validate_response_requires_ai_provider(self):
        """Response stages require ai_provider after cascade."""
        config = WorkflowConfig(
            defaults=StageConfig(approval_provider="manual"),  # no ai_provider
        )
        with pytest.raises(ConfigLoadError) as exc_info:
            validate_provider_keys(config)

        assert "ai_provider" in str(exc_info.value).lower()
        assert "response" in str(exc_info.value).lower()
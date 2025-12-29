"""Tests for config_loader error paths and default provider expansion.

Covers:
- ConfigLoadError.__init__ and __str__ (lines 10-13, 16-18)
- Malformed YAML raises ConfigLoadError (lines 65-66)
- Non-mapping YAML root raises ConfigLoadError (line 72)
- Empty YAML returns empty dict (line 69)
- _expand_default_provider function
- load_config integration with default provider expansion
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aiwf.application.config_loader import (
    ConfigLoadError,
    load_config,
    _load_yaml_mapping,
    _expand_default_provider,
)


class TestConfigLoadError:
    """Tests for ConfigLoadError exception class."""

    def test_configloaderror_str_with_path(self) -> None:
        """ConfigLoadError.__str__ includes path when provided."""
        path = Path("/some/config.yml")
        error = ConfigLoadError("Failed to parse", path=path)

        result = str(error)

        assert "Failed to parse" in result
        assert str(path) in result

    def test_configloaderror_str_without_path(self) -> None:
        """ConfigLoadError.__str__ returns message only when path is None."""
        error = ConfigLoadError("General failure")

        result = str(error)

        assert result == "General failure"

    def test_configloaderror_stores_cause(self) -> None:
        """ConfigLoadError stores the cause exception."""
        cause = ValueError("underlying error")
        error = ConfigLoadError("Wrapper error", cause=cause)

        assert error.cause is cause
        assert error.message == "Wrapper error"

    def test_configloaderror_stores_path(self) -> None:
        """ConfigLoadError stores the path."""
        path = Path("/path/to/config.yml")
        error = ConfigLoadError("Error", path=path)

        assert error.path == path


class TestLoadYamlMapping:
    """Tests for _load_yaml_mapping function."""

    def test_load_yaml_malformed_raises_configloaderror(self, tmp_path: Path) -> None:
        """Malformed YAML raises ConfigLoadError."""
        config_file = tmp_path / "malformed.yml"
        config_file.write_text(
            "profile: jpa-mt\n  invalid indentation\n: broken",
            encoding="utf-8",
        )

        with pytest.raises(ConfigLoadError) as exc_info:
            _load_yaml_mapping(config_file)

        assert "Malformed YAML" in str(exc_info.value)
        assert str(config_file) in str(exc_info.value)

    def test_load_yaml_non_mapping_root_raises_configloaderror(
        self, tmp_path: Path
    ) -> None:
        """YAML with non-mapping root (e.g., list) raises ConfigLoadError."""
        config_file = tmp_path / "list_root.yml"
        config_file.write_text(
            "- item1\n- item2\n- item3",
            encoding="utf-8",
        )

        with pytest.raises(ConfigLoadError) as exc_info:
            _load_yaml_mapping(config_file)

        assert "YAML root must be a mapping" in str(exc_info.value)
        assert str(config_file) in str(exc_info.value)

    def test_load_yaml_scalar_root_raises_configloaderror(
        self, tmp_path: Path
    ) -> None:
        """YAML with scalar root raises ConfigLoadError."""
        config_file = tmp_path / "scalar_root.yml"
        config_file.write_text("just a string", encoding="utf-8")

        with pytest.raises(ConfigLoadError) as exc_info:
            _load_yaml_mapping(config_file)

        assert "YAML root must be a mapping" in str(exc_info.value)

    def test_load_yaml_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty YAML file returns empty dict."""
        config_file = tmp_path / "empty.yml"
        config_file.write_text("", encoding="utf-8")

        result = _load_yaml_mapping(config_file)

        assert result == {}

    def test_load_yaml_null_content_returns_empty_dict(self, tmp_path: Path) -> None:
        """YAML with null/~ content returns empty dict."""
        config_file = tmp_path / "null.yml"
        config_file.write_text("~", encoding="utf-8")

        result = _load_yaml_mapping(config_file)

        assert result == {}

    def test_load_yaml_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Missing YAML file returns empty dict (not an error)."""
        config_file = tmp_path / "nonexistent.yml"

        result = _load_yaml_mapping(config_file)

        assert result == {}

    def test_load_yaml_valid_mapping_returns_dict(self, tmp_path: Path) -> None:
        """Valid YAML mapping returns the parsed dict."""
        config_file = tmp_path / "valid.yml"
        config_file.write_text(
            "profile: jpa-mt\nproviders:\n  planner: manual\n",
            encoding="utf-8",
        )

        result = _load_yaml_mapping(config_file)

        assert result == {"profile": "jpa-mt", "providers": {"planner": "manual"}}


class TestLoadConfig:
    """Tests for load_config function integration."""

    def test_load_config_with_malformed_project_config_raises(
        self, tmp_path: Path
    ) -> None:
        """load_config raises ConfigLoadError when project config is malformed."""
        project_root = tmp_path / "project"
        project_root.mkdir(parents=True, exist_ok=True)

        config_dir = project_root / ".aiwf"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "config.yml"
        config_file.write_text("{{invalid yaml", encoding="utf-8")

        with pytest.raises(ConfigLoadError) as exc_info:
            load_config(project_root=project_root, user_home=tmp_path / "home")

        assert "Malformed YAML" in str(exc_info.value)

    def test_load_config_with_list_project_config_raises(
        self, tmp_path: Path
    ) -> None:
        """load_config raises ConfigLoadError when project config is a list."""
        project_root = tmp_path / "project"
        project_root.mkdir(parents=True, exist_ok=True)

        config_dir = project_root / ".aiwf"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "config.yml"
        config_file.write_text("- profile: jpa-mt\n- profile: other", encoding="utf-8")

        with pytest.raises(ConfigLoadError) as exc_info:
            load_config(project_root=project_root, user_home=tmp_path / "home")

        assert "YAML root must be a mapping" in str(exc_info.value)

    def test_load_config_merges_user_and_project_configs(
        self, tmp_path: Path
    ) -> None:
        """load_config merges user and project configs correctly."""
        # Set up user config
        user_home = tmp_path / "home"
        user_config_dir = user_home / ".aiwf"
        user_config_dir.mkdir(parents=True, exist_ok=True)
        (user_config_dir / "config.yml").write_text(
            "profile: user-profile\ndev: user-dev",
            encoding="utf-8",
        )

        # Set up project config (should override user config)
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            "profile: project-profile",
            encoding="utf-8",
        )

        result = load_config(project_root=project_root, user_home=user_home)

        # Project overrides user for 'profile'
        assert result["profile"] == "project-profile"
        # User value preserved for 'dev' (not in project)
        assert result["dev"] == "user-dev"

    def test_load_config_default_standards_provider_is_scoped_layer_fs(
        self, tmp_path: Path
    ) -> None:
        """Default standards provider is scoped-layer-fs."""
        # Empty home and project dirs - should get defaults
        result = load_config(
            project_root=tmp_path / "project",
            user_home=tmp_path / "home",
        )

        assert result["default_standards_provider"] == "scoped-layer-fs"

    def test_load_config_default_standards_provider_can_be_overridden_by_user(
        self, tmp_path: Path
    ) -> None:
        """User config can override default_standards_provider."""
        user_home = tmp_path / "home"
        user_config_dir = user_home / ".aiwf"
        user_config_dir.mkdir(parents=True, exist_ok=True)
        (user_config_dir / "config.yml").write_text(
            "default_standards_provider: custom-provider",
            encoding="utf-8",
        )

        result = load_config(
            project_root=tmp_path / "project",
            user_home=user_home,
        )

        assert result["default_standards_provider"] == "custom-provider"

    def test_load_config_default_standards_provider_can_be_overridden_by_project(
        self, tmp_path: Path
    ) -> None:
        """Project config can override default_standards_provider."""
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            "default_standards_provider: project-provider",
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=tmp_path / "home",
        )

        assert result["default_standards_provider"] == "project-provider"

    def test_load_config_project_overrides_user_for_standards_provider(
        self, tmp_path: Path
    ) -> None:
        """Project config overrides user config for default_standards_provider."""
        # User config
        user_home = tmp_path / "home"
        user_config_dir = user_home / ".aiwf"
        user_config_dir.mkdir(parents=True, exist_ok=True)
        (user_config_dir / "config.yml").write_text(
            "default_standards_provider: user-provider",
            encoding="utf-8",
        )

        # Project config
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            "default_standards_provider: project-provider",
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=user_home,
        )

        # Project wins
        assert result["default_standards_provider"] == "project-provider"

    def test_load_config_empty_string_standards_provider_overrides_default(
        self, tmp_path: Path
    ) -> None:
        """Empty string in config is preserved (not treated as falsy for config merge)."""
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            'default_standards_provider: ""',
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=tmp_path / "home",
        )

        # Empty string should be stored (config merge preserves it)
        assert result["default_standards_provider"] == ""

    def test_load_config_null_standards_provider_uses_default(
        self, tmp_path: Path
    ) -> None:
        """Null/None in config falls back to built-in default."""
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        # YAML null is represented as ~ or null
        (project_config_dir / "config.yml").write_text(
            "default_standards_provider: ~",
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=tmp_path / "home",
        )

        # Null overwrites the default, so result is None
        assert result["default_standards_provider"] is None


class TestExpandDefaultProvider:
    """Tests for _expand_default_provider function."""

    def test_no_default_key_returns_input_unchanged(self) -> None:
        """When no 'default' key, returns input unchanged."""
        providers = {"planner": "claude", "generator": "manual"}

        result = _expand_default_provider(providers)

        assert result == {"planner": "claude", "generator": "manual"}

    def test_default_expands_to_all_roles(self) -> None:
        """Default key expands to all four roles."""
        providers = {"default": "claude"}

        result = _expand_default_provider(providers)

        assert result == {
            "planner": "claude",
            "generator": "claude",
            "reviewer": "claude",
            "reviser": "claude",
        }

    def test_explicit_roles_override_default(self) -> None:
        """Explicit role values override the default."""
        providers = {"default": "claude", "reviewer": "manual"}

        result = _expand_default_provider(providers)

        assert result == {
            "planner": "claude",
            "generator": "claude",
            "reviewer": "manual",  # explicit override preserved
            "reviser": "claude",
        }

    def test_all_roles_explicit_ignores_default(self) -> None:
        """When all roles are explicit, default is ignored."""
        providers = {
            "default": "claude",
            "planner": "gpt",
            "generator": "gemini",
            "reviewer": "manual",
            "reviser": "ollama",
        }

        result = _expand_default_provider(providers)

        assert result == {
            "planner": "gpt",
            "generator": "gemini",
            "reviewer": "manual",
            "reviser": "ollama",
        }

    def test_default_key_removed_from_output(self) -> None:
        """The 'default' key is not present in output."""
        providers = {"default": "claude"}

        result = _expand_default_provider(providers)

        assert "default" not in result

    def test_empty_dict_returns_empty(self) -> None:
        """Empty input returns empty output."""
        result = _expand_default_provider({})

        assert result == {}


class TestLoadConfigDefaultProviderIntegration:
    """Tests for load_config integration with default provider expansion."""

    def test_load_config_expands_default_provider(self, tmp_path: Path) -> None:
        """load_config expands providers.default to all roles."""
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            "providers:\n  default: claude\n",
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=tmp_path / "home",
        )

        assert result["providers"] == {
            "planner": "claude",
            "generator": "claude",
            "reviewer": "claude",
            "reviser": "claude",
        }

    def test_load_config_default_with_override(self, tmp_path: Path) -> None:
        """load_config preserves explicit role overrides with default."""
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            "providers:\n  default: claude\n  reviewer: manual\n",
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=tmp_path / "home",
        )

        assert result["providers"] == {
            "planner": "claude",
            "generator": "claude",
            "reviewer": "manual",
            "reviser": "claude",
        }

    def test_load_config_no_default_uses_builtin_defaults(
        self, tmp_path: Path
    ) -> None:
        """Without providers.default, uses built-in 'manual' defaults."""
        result = load_config(
            project_root=tmp_path / "project",
            user_home=tmp_path / "home",
        )

        assert result["providers"] == {
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        }

    def test_load_config_partial_providers_merged_with_defaults(
        self, tmp_path: Path
    ) -> None:
        """Partial providers config is merged with built-in defaults."""
        project_root = tmp_path / "project"
        project_config_dir = project_root / ".aiwf"
        project_config_dir.mkdir(parents=True, exist_ok=True)
        (project_config_dir / "config.yml").write_text(
            "providers:\n  planner: claude\n",
            encoding="utf-8",
        )

        result = load_config(
            project_root=project_root,
            user_home=tmp_path / "home",
        )

        # planner overridden, others keep defaults
        assert result["providers"] == {
            "planner": "claude",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        }

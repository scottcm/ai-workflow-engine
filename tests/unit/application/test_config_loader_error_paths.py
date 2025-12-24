"""Tests for config_loader error paths.

Covers:
- ConfigLoadError.__init__ and __str__ (lines 10-13, 16-18)
- Malformed YAML raises ConfigLoadError (lines 65-66)
- Non-mapping YAML root raises ConfigLoadError (line 72)
- Empty YAML returns empty dict (line 69)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aiwf.application.config_loader import (
    ConfigLoadError,
    load_config,
    _load_yaml_mapping,
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

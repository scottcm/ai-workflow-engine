"""Unit tests for profile discovery module.

Tests the discovery of profiles from:
1. Local directory (~/.aiwf/profiles/)
2. Entry points (aiwf.profiles group)

Per ADR-0008 Phase 2:
- Entry points override local profiles on name collision
- Failed profile loads are logged but don't crash CLI
- Profiles without register() function are skipped
"""
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import click
import pytest

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.profiles.workflow_profile import WorkflowProfile

if TYPE_CHECKING:
    from aiwf.interface.cli.profile_discovery import RegisterFn


class MockProfile(WorkflowProfile):
    """Mock profile for testing."""

    @classmethod
    def get_metadata(cls) -> dict:
        return {
            "name": "mock-profile",
            "description": "Mock profile for testing",
            "target_stack": "Test",
            "scopes": ["test"],
            "phases": ["planning", "generation"],
            "requires_config": False,
            "config_keys": [],
        }

    def generate_planning_prompt(self, context: dict) -> str:
        return "planning prompt"

    def generate_generation_prompt(self, context: dict) -> str:
        return "generation prompt"

    def generate_review_prompt(self, context: dict) -> str:
        return "review prompt"

    def generate_revision_prompt(self, context: dict) -> str:
        return "revision prompt"

    def process_planning_response(self, content: str):
        pass

    def process_generation_response(self, content: str, session_dir: Path, iteration: int):
        pass

    def process_review_response(self, content: str):
        pass

    def process_revision_response(self, content: str, session_dir: Path, iteration: int):
        pass


class MockProfile2(MockProfile):
    """Second mock profile for testing collisions."""

    @classmethod
    def get_metadata(cls) -> dict:
        return {
            "name": "mock-profile-2",
            "description": "Second mock profile",
            "target_stack": "Test",
            "scopes": ["test"],
            "phases": ["planning"],
            "requires_config": False,
            "config_keys": [],
        }


@pytest.fixture
def clean_registry():
    """Provides a clean ProfileFactory registry for tests.

    Saves and restores the original registry state so tests don't affect
    other tests that depend on registered profiles.
    """
    # Save original registry state using public API
    original = ProfileFactory.snapshot()

    # Clear for clean test
    ProfileFactory.clear()
    yield

    # Restore original registry using public API
    ProfileFactory.restore(original)


class TestProfileFactoryMethods:
    """Tests for ProfileFactory.register() and related methods."""

    def test_register_adds_profile_to_registry(self, clean_registry):
        """ProfileFactory.register() adds profile class to registry."""
        ProfileFactory.register("test-profile", MockProfile)

        assert ProfileFactory.is_registered("test-profile")
        assert ProfileFactory.get("test-profile") is MockProfile

    def test_register_overwrites_existing(self, clean_registry):
        """ProfileFactory.register() overwrites existing registration."""
        ProfileFactory.register("test-profile", MockProfile)
        ProfileFactory.register("test-profile", MockProfile2)

        assert ProfileFactory.get("test-profile") is MockProfile2

    def test_list_profiles_returns_registered_names(self, clean_registry):
        """ProfileFactory.list_profiles() returns all registered names."""
        ProfileFactory.register("profile-a", MockProfile)
        ProfileFactory.register("profile-b", MockProfile2)

        names = ProfileFactory.list_profiles()

        assert "profile-a" in names
        assert "profile-b" in names
        assert len(names) == 2

    def test_clear_removes_all_registrations(self, clean_registry):
        """ProfileFactory.clear() removes all registered profiles."""
        ProfileFactory.register("profile-a", MockProfile)
        ProfileFactory.register("profile-b", MockProfile2)

        ProfileFactory.clear()

        assert ProfileFactory.list_profiles() == []


class TestLocalProfileDiscovery:
    """Tests for _discover_local_profiles()."""

    def test_discovers_profiles_from_local_directory(self, tmp_path, clean_registry):
        """Local profiles are discovered from ~/.aiwf/profiles/."""
        from aiwf.interface.cli.profile_discovery import _discover_local_profiles

        # Create local profile directory structure
        profiles_dir = tmp_path / ".aiwf" / "profiles" / "my-local"
        profiles_dir.mkdir(parents=True)

        # Create __init__.py with register function
        init_content = '''
import click

class LocalProfile:
    @classmethod
    def get_metadata(cls):
        return {"name": "my-local", "description": "Local profile"}

def register(cli_group):
    @cli_group.command("info")
    def info():
        click.echo("Local profile info")
    return LocalProfile
'''
        (profiles_dir / "__init__.py").write_text(init_content)

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            registered = _discover_local_profiles(cli)

        assert "my-local" in registered
        assert "local:" in registered["my-local"]
        assert ProfileFactory.is_registered("my-local")

    def test_skips_profiles_without_register_function(self, tmp_path, caplog):
        """Profiles without register() function are skipped with warning."""
        from aiwf.interface.cli.profile_discovery import _discover_local_profiles

        # Create profile without register function
        profiles_dir = tmp_path / ".aiwf" / "profiles" / "no-register"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "__init__.py").write_text("# No register function\n")

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            registered = _discover_local_profiles(cli)

        assert "no-register" not in registered
        assert not ProfileFactory.is_registered("no-register")

    def test_skips_non_directory_entries(self, tmp_path):
        """Non-directory entries in profiles folder are skipped."""
        from aiwf.interface.cli.profile_discovery import _discover_local_profiles

        profiles_base = tmp_path / ".aiwf" / "profiles"
        profiles_base.mkdir(parents=True)
        # Create a file, not a directory
        (profiles_base / "not-a-profile.txt").write_text("just a file")

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            registered = _discover_local_profiles(cli)

        assert registered == {}

    def test_skips_directory_without_init_file(self, tmp_path):
        """Directories without __init__.py are skipped."""
        from aiwf.interface.cli.profile_discovery import _discover_local_profiles

        profiles_dir = tmp_path / ".aiwf" / "profiles" / "empty-profile"
        profiles_dir.mkdir(parents=True)
        # No __init__.py

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            registered = _discover_local_profiles(cli)

        assert "empty-profile" not in registered

    def test_handles_missing_profiles_directory(self, tmp_path):
        """Returns empty dict if ~/.aiwf/profiles/ doesn't exist."""
        from aiwf.interface.cli.profile_discovery import _discover_local_profiles

        # Don't create the profiles directory
        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            registered = _discover_local_profiles(cli)

        assert registered == {}

    def test_failed_profile_load_doesnt_crash(self, tmp_path, caplog):
        """Failed profile load logs warning but continues."""
        from aiwf.interface.cli.profile_discovery import _discover_local_profiles

        profiles_dir = tmp_path / ".aiwf" / "profiles" / "broken-profile"
        profiles_dir.mkdir(parents=True)
        # Create invalid Python
        (profiles_dir / "__init__.py").write_text("def register(: syntax error")

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            # Should not raise
            registered = _discover_local_profiles(cli)

        assert "broken-profile" not in registered


class TestEntryPointDiscovery:
    """Tests for _discover_entrypoint_profiles()."""

    def test_discovers_profiles_from_entry_points(self, clean_registry):
        """Entry point profiles are discovered."""
        from aiwf.interface.cli.profile_discovery import _discover_entrypoint_profiles

        # Mock entry point
        mock_ep = MagicMock()
        mock_ep.name = "ep-profile"
        mock_ep.value = "some.module:register"
        mock_ep.load.return_value = lambda cli_group: MockProfile

        cli = click.Group(name="aiwf")

        with patch(
            "aiwf.interface.cli.profile_discovery.entry_points",
            return_value=[mock_ep]
        ):
            registered = _discover_entrypoint_profiles(cli)

        assert "ep-profile" in registered
        assert "entrypoint:" in registered["ep-profile"]
        assert ProfileFactory.is_registered("ep-profile")

    def test_failed_entry_point_load_doesnt_crash(self, caplog):
        """Failed entry point load logs warning but continues."""
        from aiwf.interface.cli.profile_discovery import _discover_entrypoint_profiles

        mock_ep = MagicMock()
        mock_ep.name = "broken-ep"
        mock_ep.value = "some.broken:register"
        mock_ep.load.side_effect = ImportError("Module not found")

        cli = click.Group(name="aiwf")

        with patch(
            "aiwf.interface.cli.profile_discovery.entry_points",
            return_value=[mock_ep]
        ):
            # Should not raise
            registered = _discover_entrypoint_profiles(cli)

        assert "broken-ep" not in registered


class TestDiscoverAndRegisterProfiles:
    """Tests for discover_and_register_profiles()."""

    def test_entry_points_override_local_profiles(self, tmp_path, caplog, clean_registry):
        """Entry point profiles override local profiles with same name."""
        from aiwf.interface.cli.profile_discovery import discover_and_register_profiles

        # Create local profile
        profiles_dir = tmp_path / ".aiwf" / "profiles" / "collision"
        profiles_dir.mkdir(parents=True)
        init_content = '''
import click

class LocalCollision:
    @classmethod
    def get_metadata(cls):
        return {"name": "collision-local", "description": "Local version"}

def register(cli_group):
    return LocalCollision
'''
        (profiles_dir / "__init__.py").write_text(init_content)

        # Mock entry point with same name
        mock_ep = MagicMock()
        mock_ep.name = "collision"
        mock_ep.value = "some.module:register"
        mock_ep.load.return_value = lambda cli_group: MockProfile2

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            with patch(
                "aiwf.interface.cli.profile_discovery.entry_points",
                return_value=[mock_ep]
            ):
                registered = discover_and_register_profiles(cli)

        # Entry point should win
        assert "entrypoint:" in registered["collision"]
        # Profile factory should have the entry point version
        assert ProfileFactory.get("collision") is MockProfile2

    def test_name_collision_logs_info(self, tmp_path, caplog, clean_registry):
        """Name collision is logged for discoverability."""
        import logging
        from aiwf.interface.cli.profile_discovery import discover_and_register_profiles

        # Create local profile
        profiles_dir = tmp_path / ".aiwf" / "profiles" / "collision"
        profiles_dir.mkdir(parents=True)
        init_content = '''
import click

class LocalCollision:
    @classmethod
    def get_metadata(cls):
        return {"name": "collision", "description": "Local"}

def register(cli_group):
    return LocalCollision
'''
        (profiles_dir / "__init__.py").write_text(init_content)

        # Mock entry point with same name
        mock_ep = MagicMock()
        mock_ep.name = "collision"
        mock_ep.value = "some.module:register"
        mock_ep.load.return_value = lambda cli_group: MockProfile2

        cli = click.Group(name="aiwf")

        with caplog.at_level(logging.INFO):
            with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
                with patch(
                    "aiwf.interface.cli.profile_discovery.entry_points",
                    return_value=[mock_ep]
                ):
                    discover_and_register_profiles(cli)

        assert any("overrides" in record.message for record in caplog.records)

    def test_adds_command_groups_to_cli(self, tmp_path, clean_registry):
        """Profile command groups are added to CLI."""
        from aiwf.interface.cli.profile_discovery import discover_and_register_profiles

        # Create local profile
        profiles_dir = tmp_path / ".aiwf" / "profiles" / "my-profile"
        profiles_dir.mkdir(parents=True)
        init_content = '''
import click

class MyProfile:
    @classmethod
    def get_metadata(cls):
        return {"name": "my-profile", "description": "Test"}

def register(cli_group):
    @cli_group.command("init")
    def init():
        click.echo("Init command")
    return MyProfile
'''
        (profiles_dir / "__init__.py").write_text(init_content)

        cli = click.Group(name="aiwf")

        with patch("aiwf.interface.cli.profile_discovery.Path.home", return_value=tmp_path):
            with patch(
                "aiwf.interface.cli.profile_discovery.entry_points",
                return_value=[]
            ):
                discover_and_register_profiles(cli)

        # Check that profile group was added to CLI
        assert "my-profile" in cli.commands
        profile_group = cli.commands["my-profile"]
        assert isinstance(profile_group, click.Group)
        assert "init" in profile_group.commands
"""Unit tests for CLI validate command."""

import json
import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest.mock import patch, MagicMock

from aiwf.interface.cli.cli import cli


class TestValidateCommand:
    """Tests for the validate CLI command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_config(self, tmp_path: Path):
        """Mock load_config to return test configuration."""
        return {
            "profile": "jpa-mt",
            "providers": {"planner": "manual"},
            "dev": "test-dev",
        }

    def test_validate_ai_provider_passes(self, runner, mock_config):
        """validate ai <key> validates specific AI provider."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            # Manual provider should always pass
            result = runner.invoke(cli, ["validate", "ai", "manual"])

        assert result.exit_code == 0
        assert "ai:manual: OK" in result.output
        assert "1 of 1 providers ready" in result.output

    def test_validate_all_ai_providers(self, runner, mock_config):
        """validate ai validates all registered AI providers."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            result = runner.invoke(cli, ["validate", "ai"])

        assert result.exit_code == 0
        assert "manual: OK" in result.output

    def test_validate_unknown_provider_fails(self, runner, mock_config):
        """validate ai <unknown> fails for unregistered provider."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            result = runner.invoke(cli, ["validate", "ai", "nonexistent"])

        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_validate_json_output(self, runner, mock_config):
        """--json flag produces valid JSON output."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            result = runner.invoke(cli, ["--json", "validate", "ai", "manual"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["command"] == "validate"
        assert output["exit_code"] == 0
        assert output["all_passed"] is True
        assert len(output["results"]) == 1
        assert output["results"][0]["provider_type"] == "ai"
        assert output["results"][0]["provider_key"] == "manual"
        assert output["results"][0]["passed"] is True

    def test_validate_json_output_on_failure(self, runner, mock_config):
        """--json flag produces valid JSON output on failure."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            result = runner.invoke(cli, ["--json", "validate", "ai", "nonexistent"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["exit_code"] == 1
        assert output["all_passed"] is False
        assert output["results"][0]["passed"] is False
        assert output["results"][0]["error"] is not None

    def test_validate_standards_provider_with_mock(
        self, runner, mock_config, tmp_path: Path
    ):
        """validate standards validates standards providers and reports success."""
        # Create a mock standards root
        standards_root = tmp_path / "standards"
        standards_root.mkdir()

        mock_profile = MagicMock()
        mock_profile.get_standards_config.return_value = {
            "standards": {"root": str(standards_root)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {"entity": []},
        }

        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            with patch(
                "aiwf.domain.profiles.profile_factory.ProfileFactory.is_registered",
                return_value=True,
            ):
                with patch(
                    "aiwf.domain.profiles.profile_factory.ProfileFactory.create",
                    return_value=mock_profile,
                ):
                    result = runner.invoke(
                        cli, ["validate", "standards", "scoped-layer-fs"]
                    )

        # Assert successful validation
        assert result.exit_code == 0
        assert "standards:scoped-layer-fs: OK" in result.output
        assert "1 of 1 providers ready" in result.output

    def test_validate_all_validates_both_types(self, runner, mock_config):
        """validate all validates all provider types."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            result = runner.invoke(cli, ["validate", "all"])

        # Should include AI providers at minimum
        assert "ai:" in result.output
        # Should include standards providers
        assert "standards:" in result.output

    def test_exit_code_on_mixed_results(self, runner, mock_config):
        """Exit code is 1 when any validation fails."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            # Request validation of a known-good and known-bad provider
            result = runner.invoke(cli, ["--json", "validate", "ai", "nonexistent"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["all_passed"] is False

    def test_profile_option_for_standards(self, runner, mock_config, tmp_path: Path):
        """--profile option specifies profile for standards config and validates successfully."""
        standards_root = tmp_path / "standards"
        standards_root.mkdir()

        mock_profile = MagicMock()
        mock_profile.get_standards_config.return_value = {
            "standards": {"root": str(standards_root)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {"entity": []},
        }

        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            with patch(
                "aiwf.domain.profiles.profile_factory.ProfileFactory.is_registered",
                return_value=True,
            ):
                with patch(
                    "aiwf.domain.profiles.profile_factory.ProfileFactory.create",
                    return_value=mock_profile,
                ) as mock_factory:
                    result = runner.invoke(
                        cli,
                        [
                            "validate",
                            "standards",
                            "scoped-layer-fs",
                            "--profile",
                            "jpa-mt",
                        ],
                    )

        # Verify ProfileFactory.create was called with the specified profile
        mock_factory.assert_called_with("jpa-mt")
        # Verify successful validation outcome
        assert result.exit_code == 0
        assert "standards:scoped-layer-fs: OK" in result.output

    def test_validate_requires_provider_type(self, runner):
        """validate command requires provider_type argument."""
        result = runner.invoke(cli, ["validate"])

        assert result.exit_code == 2  # Click error for missing argument
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_validate_invalid_provider_type(self, runner):
        """validate command rejects invalid provider_type."""
        result = runner.invoke(cli, ["validate", "invalid"])

        assert result.exit_code == 2  # Click error for invalid choice

    def test_validate_standards_missing_profile_shows_error(self, runner):
        """validate standards shows error when no profile available."""
        # Config without profile key
        config_no_profile = {
            "providers": {"planner": "manual"},
        }

        with patch("aiwf.interface.cli.cli.load_config", return_value=config_no_profile):
            result = runner.invoke(
                cli, ["validate", "standards", "scoped-layer-fs"]
            )

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "Profile is required" in result.output

    def test_validate_standards_unregistered_profile_shows_error(self, runner, mock_config):
        """validate standards shows error when profile is not registered."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            with patch(
                "aiwf.domain.profiles.profile_factory.ProfileFactory.is_registered",
                return_value=False,
            ):
                result = runner.invoke(
                    cli, ["validate", "standards", "scoped-layer-fs"]
                )

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "Profile not registered" in result.output

    def test_validate_standards_profile_load_failure_shows_error(
        self, runner, mock_config
    ):
        """validate standards shows error when profile fails to load."""
        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            with patch(
                "aiwf.domain.profiles.profile_factory.ProfileFactory.is_registered",
                return_value=True,
            ):
                with patch(
                    "aiwf.domain.profiles.profile_factory.ProfileFactory.create",
                    side_effect=Exception("Profile config invalid"),
                ):
                    result = runner.invoke(
                        cli, ["validate", "standards", "scoped-layer-fs"]
                    )

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "Failed to load profile" in result.output
        assert "Profile config invalid" in result.output

    def test_validate_standards_json_output_on_success(
        self, runner, mock_config, tmp_path: Path
    ):
        """--json flag produces valid JSON output for standards validation."""
        standards_root = tmp_path / "standards"
        standards_root.mkdir()

        mock_profile = MagicMock()
        mock_profile.get_standards_config.return_value = {
            "standards": {"root": str(standards_root)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {"entity": []},
        }

        with patch("aiwf.interface.cli.cli.load_config", return_value=mock_config):
            with patch(
                "aiwf.domain.profiles.profile_factory.ProfileFactory.is_registered",
                return_value=True,
            ):
                with patch(
                    "aiwf.domain.profiles.profile_factory.ProfileFactory.create",
                    return_value=mock_profile,
                ):
                    result = runner.invoke(
                        cli, ["--json", "validate", "standards", "scoped-layer-fs"]
                    )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["command"] == "validate"
        assert output["all_passed"] is True
        assert output["results"][0]["provider_type"] == "standards"
        assert output["results"][0]["provider_key"] == "scoped-layer-fs"
        assert output["results"][0]["passed"] is True
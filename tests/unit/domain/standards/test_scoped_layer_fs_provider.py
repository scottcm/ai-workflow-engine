"""Unit tests for ScopedLayerFsProvider."""

import pytest
from pathlib import Path
from typing import Any

from aiwf.domain.standards.scoped_layer_fs_provider import ScopedLayerFsProvider
from aiwf.domain.errors import ProviderError


class TestScopedLayerFsProvider:
    """Tests for ScopedLayerFsProvider."""

    def test_get_metadata_returns_expected_structure(self):
        """get_metadata returns expected metadata structure."""
        metadata = ScopedLayerFsProvider.get_metadata()

        assert metadata["name"] == "scoped-layer-fs"
        assert "description" in metadata
        assert metadata["requires_config"] is True
        assert "standards.root" in metadata["config_keys"]
        # Connection timeout is None for filesystem provider (no network connection phase)
        assert metadata["default_connection_timeout"] is None
        assert metadata["default_response_timeout"] == 30

    def test_validate_raises_on_empty_root(self):
        """validate raises ProviderError when standards root is empty."""
        provider = ScopedLayerFsProvider({})

        with pytest.raises(ProviderError) as exc_info:
            provider.validate()

        assert "not configured" in str(exc_info.value)

    def test_validate_raises_on_missing_root(self, tmp_path: Path):
        """validate raises ProviderError when standards root doesn't exist."""
        config = {"standards": {"root": str(tmp_path / "nonexistent")}}
        provider = ScopedLayerFsProvider(config)

        with pytest.raises(ProviderError) as exc_info:
            provider.validate()

        assert "not found" in str(exc_info.value)

    def test_validate_raises_on_file_not_directory(self, tmp_path: Path):
        """validate raises ProviderError when standards root is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        config = {"standards": {"root": str(file_path)}}
        provider = ScopedLayerFsProvider(config)

        with pytest.raises(ProviderError) as exc_info:
            provider.validate()

        assert "not a directory" in str(exc_info.value)

    def test_validate_raises_on_no_scopes(self, tmp_path: Path):
        """validate raises ProviderError when no scopes configured."""
        config = {"standards": {"root": str(tmp_path)}, "scopes": {}}
        provider = ScopedLayerFsProvider(config)

        with pytest.raises(ProviderError) as exc_info:
            provider.validate()

        assert "No scopes configured" in str(exc_info.value)

    def test_validate_passes_with_valid_config(self, tmp_path: Path):
        """validate passes when configuration is valid."""
        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {"entity": ["entity.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        # Should not raise
        provider.validate()

    def test_create_bundle_raises_on_unknown_scope(self, tmp_path: Path):
        """create_bundle raises ValueError for unknown scope."""
        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {"entity": ["entity.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        with pytest.raises(ValueError) as exc_info:
            provider.create_bundle({"scope": "unknown"})

        assert "Unknown scope" in str(exc_info.value)

    def test_create_bundle_raises_on_missing_file(self, tmp_path: Path):
        """create_bundle raises ProviderError when standards file is missing."""
        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {"entity": ["entity.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        with pytest.raises(ProviderError) as exc_info:
            provider.create_bundle({"scope": "domain"})

        assert "not found" in str(exc_info.value)

    def test_create_bundle_concatenates_files(self, tmp_path: Path):
        """create_bundle correctly concatenates standards files."""
        # Create standards files
        (tmp_path / "coding.md").write_text("# Coding Standards\n")
        (tmp_path / "entity.md").write_text("# Entity Standards\n")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {
                "_universal": ["coding.md"],
                "entity": ["entity.md"],
            },
        }
        provider = ScopedLayerFsProvider(config)

        bundle = provider.create_bundle({"scope": "domain"})

        assert "--- coding.md ---" in bundle
        assert "# Coding Standards" in bundle
        assert "--- entity.md ---" in bundle
        assert "# Entity Standards" in bundle

    def test_create_bundle_respects_layer_order(self, tmp_path: Path):
        """create_bundle respects layer ordering from scope."""
        # Create standards files
        (tmp_path / "file1.md").write_text("File 1")
        (tmp_path / "file2.md").write_text("File 2")
        (tmp_path / "file3.md").write_text("File 3")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"vertical": {"layers": ["layer1", "layer2"]}},
            "layer_standards": {
                "layer1": ["file1.md"],
                "layer2": ["file2.md", "file3.md"],
            },
        }
        provider = ScopedLayerFsProvider(config)

        bundle = provider.create_bundle({"scope": "vertical"})

        # Verify order: file1 before file2 before file3
        pos1 = bundle.index("File 1")
        pos2 = bundle.index("File 2")
        pos3 = bundle.index("File 3")
        assert pos1 < pos2 < pos3

    def test_create_bundle_deduplicates_files(self, tmp_path: Path):
        """create_bundle deduplicates files that appear in multiple layers."""
        (tmp_path / "shared.md").write_text("Shared content")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["layer1", "layer2"]}},
            "layer_standards": {
                "layer1": ["shared.md"],
                "layer2": ["shared.md"],  # Duplicate
            },
        }
        provider = ScopedLayerFsProvider(config)

        bundle = provider.create_bundle({"scope": "domain"})

        # Should only appear once
        assert bundle.count("--- shared.md ---") == 1

    def test_create_bundle_uses_default_timeouts(self, tmp_path: Path):
        """create_bundle uses default timeouts from metadata."""
        (tmp_path / "test.md").write_text("Test")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["layer1"]}},
            "layer_standards": {"layer1": ["test.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        # Should complete without timeout error
        bundle = provider.create_bundle({"scope": "domain"})
        assert "Test" in bundle

    def test_create_bundle_adds_newline_if_missing(self, tmp_path: Path):
        """create_bundle adds trailing newline if file doesn't have one."""
        (tmp_path / "no_newline.md").write_text("Content without newline")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["layer1"]}},
            "layer_standards": {"layer1": ["no_newline.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        bundle = provider.create_bundle({"scope": "domain"})

        # Check that content ends with newline
        assert bundle.endswith("\n")

    def test_create_bundle_accepts_explicit_timeout_parameters(self, tmp_path: Path):
        """create_bundle accepts explicit timeout parameters without error."""
        (tmp_path / "test.md").write_text("Test content")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["layer1"]}},
            "layer_standards": {"layer1": ["test.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        # Should complete successfully with explicit timeout values
        bundle = provider.create_bundle(
            {"scope": "domain"},
            connection_timeout=10,
            response_timeout=60,
        )
        assert "Test content" in bundle

    def test_create_bundle_accepts_zero_timeouts(self, tmp_path: Path):
        """create_bundle accepts 0 for timeouts (meaning no timeout)."""
        (tmp_path / "test.md").write_text("Test content")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["layer1"]}},
            "layer_standards": {"layer1": ["test.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        # 0 means "no timeout" - should complete successfully
        bundle = provider.create_bundle(
            {"scope": "domain"},
            connection_timeout=0,
            response_timeout=0,
        )
        assert "Test content" in bundle

    def test_create_bundle_accepts_none_timeouts(self, tmp_path: Path):
        """create_bundle accepts None for timeouts (use defaults)."""
        (tmp_path / "test.md").write_text("Test content")

        config = {
            "standards": {"root": str(tmp_path)},
            "scopes": {"domain": {"layers": ["layer1"]}},
            "layer_standards": {"layer1": ["test.md"]},
        }
        provider = ScopedLayerFsProvider(config)

        # None means "use default" - should complete successfully
        bundle = provider.create_bundle(
            {"scope": "domain"},
            connection_timeout=None,
            response_timeout=None,
        )
        assert "Test content" in bundle
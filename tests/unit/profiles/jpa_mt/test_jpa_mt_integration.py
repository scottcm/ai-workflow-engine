"""
Integration tests for JPA-MT profile configuration and standards provider.

Tests the full chain:
- Config validation
- Profile instantiation
- Standards provider creation via factory
- Standards bundle generation
"""

import os
import pytest
from pathlib import Path

# Import the profile package to trigger registration
import profiles.jpa_mt

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.standards import StandardsProviderFactory


class TestJpaMtProfileIntegration:
    """Test JPA-MT profile end-to-end configuration and provider creation."""

    def test_profile_factory_creates_jpa_mt_profile(self, monkeypatch):
        """Test profile can be created via factory with valid config."""
        monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")

        config = {
            "standards": {"root": "${STANDARDS_DIR}"},
            "scopes": {"domain": {"layers": ["entity", "repository"]}},
            "layer_standards": {
                "_universal": ["ORG.md"],
                "entity": ["JPA_AND_DATABASE.md"],
                "repository": ["JPA_AND_DATABASE.md"]
            }
        }

        profile = ProfileFactory.create("jpa-mt", config=config)

        # Verify profile was created
        assert profile is not None
        assert profile.config["standards"]["root"] == "/tmp/standards"

    def test_profile_provides_standards_provider_via_factory(self, monkeypatch, tmp_path):
        """Test that profile config can create a working standards provider via factory."""
        # Setup: Create actual standards files
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()
        (standards_dir / "ORG.md").write_text("# Organization Standards\n")
        (standards_dir / "JPA.md").write_text("# JPA Standards\n")

        monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

        config = {
            "standards": {"root": "${STANDARDS_DIR}"},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {
                "_universal": ["ORG.md"],
                "entity": ["JPA.md"]
            }
        }

        # Act: Get provider via factory using profile's config
        profile = ProfileFactory.create("jpa-mt", config=config)
        provider_key = profile.get_default_standards_provider_key()
        standards_config = profile.get_standards_config()
        provider = StandardsProviderFactory.create(provider_key, standards_config)

        # Assert: Provider can create a bundle with correct content
        context = {"scope": "domain"}
        bundle = provider.create_bundle(context)

        assert "--- ORG.md ---" in bundle
        assert "# Organization Standards" in bundle
        assert "--- JPA.md ---" in bundle
        assert "# JPA Standards" in bundle

    def test_standards_provider_creates_bundle(self, tmp_path, monkeypatch):
        """Test standards provider can create bundle from actual files."""
        # Create test standards files
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()

        (standards_dir / "ORG.md").write_text("# Organization Standards\n")
        (standards_dir / "JPA.md").write_text("# JPA Standards\n")

        monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

        config = {
            "standards": {"root": "${STANDARDS_DIR}"},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {
                "_universal": ["ORG.md"],
                "entity": ["JPA.md"]
            }
        }

        profile = ProfileFactory.create("jpa-mt", config=config)
        provider_key = profile.get_default_standards_provider_key()
        standards_config = profile.get_standards_config()
        provider = StandardsProviderFactory.create(provider_key, standards_config)

        # Create bundle
        context = {"scope": "domain", "entity": "Product"}
        bundle = provider.create_bundle(context)

        # Verify bundle contains both files
        assert "--- JPA.md ---" in bundle
        assert "--- ORG.md ---" in bundle
        assert "# JPA Standards" in bundle
        assert "# Organization Standards" in bundle

    def test_standards_files_deduplicated(self, tmp_path, monkeypatch):
        """Test that duplicate standards files are only included once."""
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()

        (standards_dir / "SHARED.md").write_text("# Shared Standards\n")

        monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

        config = {
            "standards": {"root": "${STANDARDS_DIR}"},
            "scopes": {"domain": {"layers": ["entity", "repository"]}},
            "layer_standards": {
                "_universal": ["SHARED.md"],
                "entity": ["SHARED.md"],      # Duplicate
                "repository": ["SHARED.md"]   # Duplicate
            }
        }

        profile = ProfileFactory.create("jpa-mt", config=config)
        provider_key = profile.get_default_standards_provider_key()
        standards_config = profile.get_standards_config()
        provider = StandardsProviderFactory.create(provider_key, standards_config)

        context = {"scope": "domain"}
        bundle = provider.create_bundle(context)

        # Should only appear once
        count = bundle.count("--- SHARED.md ---")
        assert count == 1

    def test_profile_with_subdirectory_paths(self, tmp_path, monkeypatch):
        """Test standards files in subdirectories are handled correctly."""
        standards_dir = tmp_path / "standards"
        db_dir = standards_dir / "db" / "java"
        db_dir.mkdir(parents=True)

        (db_dir / "JPA.md").write_text("# JPA Standards\n")

        monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

        config = {
            "standards": {"root": "${STANDARDS_DIR}"},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {
                "entity": ["db/java/JPA.md"]  # Subdirectory path
            }
        }

        profile = ProfileFactory.create("jpa-mt", config=config)
        provider_key = profile.get_default_standards_provider_key()
        standards_config = profile.get_standards_config()
        provider = StandardsProviderFactory.create(provider_key, standards_config)

        context = {"scope": "domain"}
        bundle = provider.create_bundle(context)

        assert "--- db/java/JPA.md ---" in bundle
        assert "# JPA Standards" in bundle
    
    def test_invalid_config_raises_validation_error(self, monkeypatch):
        """Test that invalid config is rejected at profile creation."""
        monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
        
        # Invalid: absolute path in layer_standards
        config = {
            "standards": {"root": "${STANDARDS_DIR}"},
            "scopes": {"domain": {"layers": ["entity"]}},
            "layer_standards": {
                "entity": ["/absolute/path.md"]  # Invalid
            }
        }
        
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProfileFactory.create("jpa-mt", config=config)
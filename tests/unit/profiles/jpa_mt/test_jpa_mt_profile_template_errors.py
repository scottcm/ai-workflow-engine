"""Tests for JpaMtProfile template error paths.

Covers:
- Template not found raises FileNotFoundError (line 46)
- Circular include detection raises RuntimeError (line 71)
- Include file not found raises FileNotFoundError (line 74)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.domain.profiles.profile_factory import ProfileFactory


@pytest.fixture
def jpa_mt_profile(tmp_path, monkeypatch):
    """Create JPA-MT profile with test standards directory."""
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))
    return ProfileFactory.create("jpa-mt")


class TestLoadTemplateErrors:
    """Tests for _load_template error paths."""

    def test_load_template_missing_raises_filenotfounderror(self, jpa_mt_profile) -> None:
        """_load_template raises FileNotFoundError when template doesn't exist."""
        # Use a scope that doesn't have a template file
        with pytest.raises(FileNotFoundError) as exc_info:
            jpa_mt_profile._load_template("planning", "nonexistent-scope")

        assert "Template not found" in str(exc_info.value)
        assert "nonexistent-scope" in str(exc_info.value)

    def test_load_template_missing_phase_raises_filenotfounderror(self, jpa_mt_profile) -> None:
        """_load_template raises FileNotFoundError for non-existent phase."""
        with pytest.raises(FileNotFoundError) as exc_info:
            jpa_mt_profile._load_template("nonexistent-phase", "domain")

        assert "Template not found" in str(exc_info.value)


class TestResolveIncludesErrors:
    """Tests for _resolve_includes error paths."""

    def test_resolve_includes_circular_raises_runtimeerror(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes raises RuntimeError for circular includes."""
        # Create two files that include each other
        file_a = tmp_path / "file_a.md"
        file_b = tmp_path / "file_b.md"

        file_a.write_text("Content A\n{{include: file_b.md}}", encoding="utf-8")
        file_b.write_text("Content B\n{{include: file_a.md}}", encoding="utf-8")

        content = file_a.read_text(encoding="utf-8")

        with pytest.raises(RuntimeError) as exc_info:
            jpa_mt_profile._resolve_includes(content, file_a)

        assert "Circular include" in str(exc_info.value)

    def test_resolve_includes_self_reference_raises_runtimeerror(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes raises RuntimeError for self-referencing include."""
        # Create a file that includes itself
        file_a = tmp_path / "self_ref.md"
        file_a.write_text("Content\n{{include: self_ref.md}}", encoding="utf-8")

        content = file_a.read_text(encoding="utf-8")

        with pytest.raises(RuntimeError) as exc_info:
            jpa_mt_profile._resolve_includes(content, file_a)

        assert "Circular include" in str(exc_info.value)

    def test_resolve_includes_missing_file_raises_filenotfounderror(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes raises FileNotFoundError for missing include."""
        # Create a file that includes a non-existent file
        file_a = tmp_path / "main.md"
        file_a.write_text(
            "Content\n{{include: nonexistent.md}}",
            encoding="utf-8",
        )

        content = file_a.read_text(encoding="utf-8")

        with pytest.raises(FileNotFoundError) as exc_info:
            jpa_mt_profile._resolve_includes(content, file_a)

        assert "Include not found" in str(exc_info.value)
        assert "nonexistent.md" in str(exc_info.value)

    def test_resolve_includes_nested_missing_raises_filenotfounderror(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes raises FileNotFoundError for missing nested include."""
        # Create files: main -> exists -> missing
        main = tmp_path / "main.md"
        exists = tmp_path / "exists.md"

        main.write_text("Main\n{{include: exists.md}}", encoding="utf-8")
        exists.write_text("Exists\n{{include: missing.md}}", encoding="utf-8")

        content = main.read_text(encoding="utf-8")

        with pytest.raises(FileNotFoundError) as exc_info:
            jpa_mt_profile._resolve_includes(content, main)

        assert "Include not found" in str(exc_info.value)
        assert "missing.md" in str(exc_info.value)


class TestResolveIncludesSuccess:
    """Tests for _resolve_includes success paths (regression guards)."""

    def test_resolve_includes_no_includes_returns_content(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes returns content unchanged when no includes."""
        file_a = tmp_path / "no_includes.md"
        file_a.write_text("Just plain content\nNo includes here", encoding="utf-8")

        content = file_a.read_text(encoding="utf-8")
        result = jpa_mt_profile._resolve_includes(content, file_a)

        assert result == content

    def test_resolve_includes_single_include_works(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes correctly resolves a single include."""
        main = tmp_path / "main.md"
        included = tmp_path / "included.md"

        included.write_text("INCLUDED CONTENT", encoding="utf-8")
        main.write_text("Before\n{{include: included.md}}\nAfter", encoding="utf-8")

        content = main.read_text(encoding="utf-8")
        result = jpa_mt_profile._resolve_includes(content, main)

        assert "Before" in result
        assert "INCLUDED CONTENT" in result
        assert "After" in result
        assert "{{include:" not in result

    def test_resolve_includes_nested_includes_work(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes correctly resolves nested includes."""
        main = tmp_path / "main.md"
        level1 = tmp_path / "level1.md"
        level2 = tmp_path / "level2.md"

        level2.write_text("LEVEL2", encoding="utf-8")
        level1.write_text("LEVEL1\n{{include: level2.md}}", encoding="utf-8")
        main.write_text("MAIN\n{{include: level1.md}}", encoding="utf-8")

        content = main.read_text(encoding="utf-8")
        result = jpa_mt_profile._resolve_includes(content, main)

        assert "MAIN" in result
        assert "LEVEL1" in result
        assert "LEVEL2" in result
        assert "{{include:" not in result

    def test_resolve_includes_with_whitespace_in_directive(
        self, jpa_mt_profile, tmp_path: Path
    ) -> None:
        """_resolve_includes handles whitespace in include directive."""
        main = tmp_path / "main.md"
        included = tmp_path / "included.md"

        included.write_text("INCLUDED", encoding="utf-8")
        main.write_text("{{include:   included.md  }}", encoding="utf-8")

        content = main.read_text(encoding="utf-8")
        result = jpa_mt_profile._resolve_includes(content, main)

        assert "INCLUDED" in result

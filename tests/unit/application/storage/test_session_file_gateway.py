"""Tests for SessionFileGateway."""

import pytest
from pathlib import Path

from aiwf.application.storage.session_file_gateway import SessionFileGateway


class TestWriteCodeFile:
    """Tests for write_code_file method."""

    def test_write_code_file_success(self, tmp_path: Path) -> None:
        """Test writing a valid code file."""
        gateway = SessionFileGateway(tmp_path)

        result = gateway.write_code_file(1, "Entity.java", "public class Entity {}")

        assert result.exists()
        assert result.read_text() == "public class Entity {}"
        assert result == tmp_path / "iteration-1" / "code" / "Entity.java"

    def test_write_code_file_nested_path(self, tmp_path: Path) -> None:
        """Test writing to nested directory within code dir."""
        gateway = SessionFileGateway(tmp_path)

        result = gateway.write_code_file(1, "com/example/Entity.java", "package com.example;")

        assert result.exists()
        assert result == tmp_path / "iteration-1" / "code" / "com" / "example" / "Entity.java"

    def test_write_code_file_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Test that path traversal attempts are rejected."""
        gateway = SessionFileGateway(tmp_path)

        with pytest.raises(ValueError, match="Path escapes code directory"):
            gateway.write_code_file(1, "../../../etc/passwd", "malicious content")

    def test_write_code_file_double_dot_in_middle_rejected(self, tmp_path: Path) -> None:
        """Test that .. segments in middle of path are rejected."""
        gateway = SessionFileGateway(tmp_path)

        with pytest.raises(ValueError, match="Path escapes code directory"):
            gateway.write_code_file(1, "foo/../../bar.txt", "content")

    def test_write_code_file_absolute_path_rejected(self, tmp_path: Path) -> None:
        """Test that absolute paths are rejected."""
        gateway = SessionFileGateway(tmp_path)

        # On Windows, absolute paths start with drive letter
        # On Unix, they start with /
        # Both should be rejected as they resolve outside code_dir
        with pytest.raises(ValueError, match="Path escapes code directory"):
            gateway.write_code_file(1, "/etc/passwd", "content")


class TestReadCodeFiles:
    """Tests for read_code_files method."""

    def test_read_code_files_empty(self, tmp_path: Path) -> None:
        """Test reading from non-existent code dir returns empty dict."""
        gateway = SessionFileGateway(tmp_path)

        result = gateway.read_code_files(1)

        assert result == {}

    def test_read_code_files_returns_all_files(self, tmp_path: Path) -> None:
        """Test reading returns all files with relative paths."""
        gateway = SessionFileGateway(tmp_path)
        gateway.write_code_file(1, "Entity.java", "class Entity")
        gateway.write_code_file(1, "Repository.java", "interface Repository")

        result = gateway.read_code_files(1)

        assert len(result) == 2
        assert result["Entity.java"] == "class Entity"
        assert result["Repository.java"] == "interface Repository"

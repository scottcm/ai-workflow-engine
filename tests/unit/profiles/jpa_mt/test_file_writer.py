"""
Unit tests for the JPA Multi-Tenant Profile File Writer.

This test suite defines the contract for `profiles.jpa_mt.file_writer`.
It enforces strict TDD by specifying expected behavior before implementation.

Contract:
- Input: Output directory path, Dict mapping filename -> file content.
- Output: List of pathlib.Path objects for written files.
- Constraints:
  - Must validate filenames (security + .java extension).
  - Must create output directory if missing.
  - Must write files in deterministic order (sorted by filename).
  - Must preserve content exactly (no stripping/newlines).
  - Must fail fast on any invalid filename (no files written).
  - Must not leak internal PathValidator error messages.
  - Must raise ValueError with "Invalid filename" for any name issues.
"""

import pytest
from pathlib import Path

try:
    from profiles.jpa_mt.file_writer import write_files
except ImportError:
    write_files = None

@pytest.fixture
def writer():
    """Ensure write_files is available or fail helpfully."""
    if write_files is None:
        pytest.fail("profiles.jpa_mt.file_writer.write_files not found. Implement it first.")
    return write_files

def test_write_files_happy_path(writer, tmp_path):
    """Test writing multiple valid files."""
    output_dir = tmp_path / "src"
    files = {
        "Product.java": "package com.example;\nclass Product {}",
        "ProductRepository.java": "package com.example;\ninterface ProductRepository {}",
    }
    
    written = writer(output_dir, files)
    
    # Check return value
    assert len(written) == 2
    assert isinstance(written[0], Path)
    assert written[0].name == "Product.java"
    assert written[1].name == "ProductRepository.java"
    
    # Check file system
    assert (output_dir / "Product.java").read_text(encoding="utf-8") == files["Product.java"]
    assert (output_dir / "ProductRepository.java").read_text(encoding="utf-8") == files["ProductRepository.java"]

def test_write_files_creates_directory(writer, tmp_path):
    """Test that output directory is created if it doesn't exist."""
    output_dir = tmp_path / "deep" / "nested" / "dir"
    files = {"Entity.java": "content"}
    
    writer(output_dir, files)
    
    assert output_dir.exists()
    assert (output_dir / "Entity.java").exists()

def test_write_files_deterministic_order(writer, tmp_path):
    """Test that files are written in sorted order."""
    output_dir = tmp_path
    files = {
        "C.java": "c",
        "A.java": "a",
        "B.java": "b",
    }
    
    written = writer(output_dir, files)
    
    names = [p.name for p in written]
    assert names == ["A.java", "B.java", "C.java"]

def test_write_files_invalid_filename_path_separator(writer, tmp_path):
    """Test that filename with path separator raises ValueError."""
    files = {"dir/File.java": "content"}
    
    with pytest.raises(ValueError, match="Invalid filename"):
        writer(tmp_path, files)
        
    # Ensure no file was written
    assert not any(tmp_path.iterdir())

def test_write_files_invalid_filename_parent_ref(writer, tmp_path):
    """Test that filename with parent reference raises ValueError."""
    files = {"../File.java": "content"}
    
    with pytest.raises(ValueError, match="Invalid filename"):
        writer(tmp_path, files)

def test_write_files_invalid_extension(writer, tmp_path):
    """Test that non-.java extension raises ValueError."""
    files = {"Product.txt": "content"}
    
    with pytest.raises(ValueError, match="Invalid filename"):
        writer(tmp_path, files)

def test_write_files_preserves_content_exactly(writer, tmp_path):
    """Test that content is not trimmed or modified."""
    # Content with trailing spaces and no final newline
    content = "   class Code { }   "
    files = {"Code.java": content}
    
    writer(tmp_path, files)
    
    read_content = (tmp_path / "Code.java").read_text(encoding="utf-8")
    assert read_content == content

def test_write_files_fail_fast(writer, tmp_path):
    """Test that valid files are not written if any invalid file exists."""
    files = {
        "Valid.java": "valid",
        "Invalid.txt": "invalid", # Wrong extension
    }
    
    with pytest.raises(ValueError, match="Invalid filename"):
        writer(tmp_path, files)
        
    # Ensure NOTHING was written
    assert not (tmp_path / "Valid.java").exists()
    assert not (tmp_path / "Invalid.txt").exists()

def test_write_files_directory_creation_failure(writer, tmp_path, monkeypatch):
    """Test handling of directory creation failure."""
    # Simulate a file blocking the directory creation
    (tmp_path / "blocked").touch()
    output_dir = tmp_path / "blocked" / "subdir"
    
    with pytest.raises(ValueError, match="Cannot create directory"):
        writer(output_dir, {"File.java": "content"})

def test_write_files_write_failure(writer, tmp_path, monkeypatch):
    """Test handling of write failure."""
    output_dir = tmp_path
    
    # Mock Path.write_text to fail
    def mock_write_text(*args, **kwargs):
        raise IOError("Disk full")
        
    monkeypatch.setattr("pathlib.Path.write_text", mock_write_text)
    
    with pytest.raises(ValueError, match="Failed to write file"):
        writer(output_dir, {"File.java": "content"})

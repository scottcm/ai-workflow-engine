"""
Unit tests for aiwf.domain.validation.path_validator.PathValidator.
"""

import os
import pytest
from pathlib import Path
from aiwf.domain.validation.path_validator import PathValidator, PathValidationError

class TestPathValidator:
    
    # --- Tests for existing methods ---

    def test_sanitize_entity_name_valid(self):
        """Test valid entity names."""
        assert PathValidator.sanitize_entity_name("Product") == "Product"
        assert PathValidator.sanitize_entity_name("Order-Item") == "Order-Item"
        assert PathValidator.sanitize_entity_name("User_Profile") == "User_Profile"
        assert PathValidator.sanitize_entity_name("MyEntity123") == "MyEntity123"

    def test_sanitize_entity_name_invalid(self):
        """Test invalid entity names raise PathValidationError."""
        invalid_names = [
            "",                 # Empty
            "Product/Detail",   # Slash
            "Product\\Detail",  # Backslash
            "../Product",       # Parent dir
            "Product Name",     # Space
            "Product$",         # Special char
        ]
        for name in invalid_names:
            with pytest.raises(PathValidationError):
                PathValidator.sanitize_entity_name(name)

    def test_sanitize_path_component_valid(self):
        """Test valid path components."""
        assert PathValidator.sanitize_path_component("docs") == "docs"
        assert PathValidator.sanitize_path_component("my-files") == "my-files"

    def test_sanitize_path_component_invalid(self):
        """Test invalid path components raise PathValidationError."""
        invalid_components = [
            "",             # Empty
            "dir/subdir",   # Path separator
            "dir name",     # Space
            "..",           # Parent reference (safe name pattern regex ^[a-zA-Z0-9_-]+$ doesn't match dots)
        ]
        for comp in invalid_components:
            with pytest.raises(PathValidationError):
                PathValidator.sanitize_path_component(comp)

    def test_expand_env_vars(self):
        """Test environment variable expansion."""
        os.environ["TEST_ENV_VAR"] = "/tmp/test"
        path = "${TEST_ENV_VAR}/file.txt"
        expanded = PathValidator.expand_env_vars(path)
        # On Windows, it might be C:\tmp\test depending on drive, but here we just check substitution
        # os.path.expandvars behavior depends on OS.
        # We assert the variable part is replaced.
        assert "/tmp/test" in expanded.replace("\\", "/") 
        assert "file.txt" in expanded
        
        del os.environ["TEST_ENV_VAR"]

    def test_expand_env_vars_undefined(self):
        """Test undefined env vars raise exception."""
        with pytest.raises(PathValidationError) as excinfo:
            PathValidator.expand_env_vars("${UNDEFINED_VAR_XYZ}/file.txt")
        assert "Undefined environment variables" in str(excinfo.value)

    def test_validate_relative_path_pattern_valid(self):
        valid_cases = [
            "entity/JPA_AND_DATABASE.md",
            "db/java/JPA.md",
            "db\\java\\JPA.md",
            "a/b/c.txt",
            "a\\b\\c.txt",
            "single.md",
        ]
        for p in valid_cases:
            assert PathValidator.validate_relative_path_pattern(p) == p

    def test_validate_relative_path_pattern_strips_whitespace(self):
        assert PathValidator.validate_relative_path_pattern("  entity/JPA.md  ") == "entity/JPA.md"

    def test_validate_relative_path_pattern_rejects_empty(self):
        with pytest.raises(PathValidationError):
            PathValidator.validate_relative_path_pattern("   ")

    def test_validate_relative_path_pattern_rejects_absolute_paths(self):
        invalid_cases = [
            "/etc/passwd",
            "\\windows\\system32",
            "C:\\temp\\file.txt",
            "C:/temp/file.txt",
            "\\\\server\\share\\file.txt",
        ]
        for p in invalid_cases:
            with pytest.raises(PathValidationError):
                PathValidator.validate_relative_path_pattern(p)

    def test_validate_relative_path_pattern_rejects_traversal(self):
        invalid_cases = [
            "../file.txt",
            "a/../file.txt",
            "a\\..\\file.txt",
        ]
        for p in invalid_cases:
            with pytest.raises(PathValidationError):
                PathValidator.validate_relative_path_pattern(p)

    def test_validate_relative_path_pattern_rejects_dot_segments(self):
        invalid_cases = [
            "./file.txt",
            "a/./file.txt",
            "a\\.\\file.txt",
        ]
        for p in invalid_cases:
            with pytest.raises(PathValidationError):
                PathValidator.validate_relative_path_pattern(p)

    def test_validate_within_root(self, tmp_path):
        """Test path traversal prevention."""
        root = tmp_path / "root"
        root.mkdir()
        safe_file = root / "safe.txt"
        safe_file.touch()
        
        # Valid case
        validated = PathValidator.validate_within_root(safe_file, root)
        assert validated == safe_file.resolve()
        
        # Invalid case (outside root)
        unsafe_file = tmp_path / "unsafe.txt"
        unsafe_file.touch()
        with pytest.raises(PathValidationError):
            PathValidator.validate_within_root(unsafe_file, root)

    # --- Tests for NEW method: sanitize_filename ---

    def test_sanitize_filename_valid(self):
        """Test valid filenames."""
        valid_cases = [
            "Product.java",
            "Tier-Entity.java",
            "Order_Item.java",
            "Test.spec.java",
            "MyFile.txt",
            "readme",        # No extension
            "script.sh",
            "123.456",
        ]
        for filename in valid_cases:
            assert PathValidator.sanitize_filename(filename) == filename

    def test_sanitize_filename_invalid_empty(self):
        """Test empty filename raises error."""
        with pytest.raises(PathValidationError, match="Filename cannot be empty"):
            PathValidator.sanitize_filename("")

    def test_sanitize_filename_invalid_path_separators(self):
        """Test filenames with path separators raise error."""
        # Note: ../File.java fails here too because of /
        invalid_cases = [
            "path/to/File.java",
            "path\\to\\File.java",
            "/File.java",
            "C:\\File.java",
            "../File.java" 
        ]
        for filename in invalid_cases:
            with pytest.raises(PathValidationError, match="Path separators"):
                PathValidator.sanitize_filename(filename)

    def test_sanitize_filename_invalid_parent_ref(self):
        """Test filenames with parent directory reference raise error."""
        # '..' with no separators
        with pytest.raises(PathValidationError, match="Parent directory references"):
             PathValidator.sanitize_filename("..")

    def test_sanitize_filename_invalid_dots(self):
        """Test filenames consisting only of dots or starting with dot."""
        invalid_cases = [
            ".",
            ".hidden",
            ".git",
        ]
        for filename in invalid_cases:
            with pytest.raises(PathValidationError, match="Hidden files or dot-only names"):
                PathValidator.sanitize_filename(filename)

    def test_sanitize_filename_invalid_characters(self):
        """Test filenames with invalid characters in the name part."""
        # Note: Based on contract, name part (before extension) must match SAFE_NAME_PATTERN
        invalid_cases = [
            "File$.java",
            "File#.java",
            "File Name.java", # Space
            "File*.java",
        ]
        for filename in invalid_cases:
            with pytest.raises(PathValidationError, match="Invalid filename format"):
                PathValidator.sanitize_filename(filename)

    def test_sanitize_filename_edge_cases(self):
        """Test edge cases."""
        # Unicode char
        with pytest.raises(PathValidationError):
            PathValidator.sanitize_filename("File\u2603.java")

        # Multiple dots
        assert PathValidator.sanitize_filename("my.test.file.java") == "my.test.file.java"


class TestValidateArtifactPath:
    """Tests for validate_artifact_path method."""

    # --- Valid paths ---

    def test_simple_filename(self):
        """Simple filename is valid."""
        assert PathValidator.validate_artifact_path("Customer.java") == "Customer.java"

    def test_nested_path(self):
        """Nested path with subdirectory is valid."""
        assert PathValidator.validate_artifact_path("entity/Customer.java") == "entity/Customer.java"

    def test_deeply_nested_path(self):
        """Deeply nested path is valid."""
        result = PathValidator.validate_artifact_path("com/example/entity/Customer.java")
        assert result == "com/example/entity/Customer.java"

    def test_windows_backslashes_normalized(self):
        """Windows backslashes are normalized to forward slashes."""
        assert PathValidator.validate_artifact_path("entity\\Customer.java") == "entity/Customer.java"
        assert PathValidator.validate_artifact_path("com\\example\\Customer.java") == "com/example/Customer.java"

    def test_filename_with_dots(self):
        """Filenames with multiple dots are valid."""
        assert PathValidator.validate_artifact_path("Customer.spec.java") == "Customer.spec.java"

    def test_filename_with_numbers(self):
        """Filenames with numbers are valid."""
        assert PathValidator.validate_artifact_path("Customer2.java") == "Customer2.java"

    # --- Invalid paths: empty/null ---

    def test_empty_path_rejected(self):
        """Empty path is rejected."""
        with pytest.raises(PathValidationError, match="non-empty"):
            PathValidator.validate_artifact_path("")

    def test_whitespace_only_path_rejected(self):
        """Whitespace-only path is rejected."""
        with pytest.raises(PathValidationError, match="non-empty"):
            PathValidator.validate_artifact_path("   ")

    # --- Invalid paths: absolute paths ---

    def test_absolute_path_rejected(self):
        """Absolute paths are rejected."""
        with pytest.raises(PathValidationError, match="Absolute"):
            PathValidator.validate_artifact_path("/etc/passwd")

    def test_windows_absolute_path_rejected(self):
        """Windows absolute paths are rejected."""
        with pytest.raises(PathValidationError, match="Drive-letter"):
            PathValidator.validate_artifact_path("C:\\Windows\\System32\\file.dll")

    def test_unc_path_rejected(self):
        """UNC paths are rejected (after normalization becomes //server/share which is absolute)."""
        with pytest.raises(PathValidationError, match="Absolute"):
            PathValidator.validate_artifact_path("\\\\server\\share\\file.txt")

    # --- Invalid paths: traversal ---

    def test_parent_directory_traversal_rejected(self):
        """Parent directory traversal is rejected."""
        with pytest.raises(PathValidationError, match="traversal"):
            PathValidator.validate_artifact_path("../Customer.java")

    def test_nested_traversal_rejected(self):
        """Nested traversal is rejected."""
        with pytest.raises(PathValidationError, match="traversal"):
            PathValidator.validate_artifact_path("entity/../../../etc/passwd")

    def test_current_directory_reference_rejected(self):
        """Current directory reference is rejected."""
        with pytest.raises(PathValidationError, match="Current-directory"):
            PathValidator.validate_artifact_path("./Customer.java")

    # --- Invalid paths: empty segments ---

    def test_leading_slash_rejected(self):
        """Leading slash creates empty segment - rejected as absolute."""
        with pytest.raises(PathValidationError):
            PathValidator.validate_artifact_path("/Customer.java")

    def test_trailing_slash_rejected(self):
        """Trailing slash creates empty segment."""
        with pytest.raises(PathValidationError, match="empty path segment"):
            PathValidator.validate_artifact_path("entity/")

    def test_consecutive_slashes_rejected(self):
        """Consecutive slashes create empty segment."""
        with pytest.raises(PathValidationError, match="empty path segment"):
            PathValidator.validate_artifact_path("entity//Customer.java")

    # --- Invalid paths: hidden files ---

    def test_hidden_file_rejected(self):
        """Hidden files (starting with dot) are rejected."""
        with pytest.raises(PathValidationError, match="cannot start with"):
            PathValidator.validate_artifact_path(".gitignore")

    def test_hidden_file_in_subdirectory_rejected(self):
        """Hidden files in subdirectories are rejected."""
        with pytest.raises(PathValidationError, match="cannot start with"):
            PathValidator.validate_artifact_path("config/.env")

    # --- Protected names ---

    def test_protected_name_rejected(self):
        """Protected filenames are rejected."""
        protected = {"session.json", "config.yml"}
        with pytest.raises(PathValidationError, match="protected file"):
            PathValidator.validate_artifact_path("session.json", protected_names=protected)

    def test_protected_name_in_subdirectory_allowed(self):
        """Protected name check only applies to filename, not full path."""
        protected = {"session.json"}
        # The filename is "data.json", not "session.json", so this should pass
        result = PathValidator.validate_artifact_path("session/data.json", protected_names=protected)
        assert result == "session/data.json"

    def test_protected_name_as_directory_allowed(self):
        """Directory named like protected file is allowed if filename is different."""
        protected = {"session.json"}
        # Filename is "Customer.java", directory is "session.json" (unusual but valid)
        result = PathValidator.validate_artifact_path("session.json/Customer.java", protected_names=protected)
        assert result == "session.json/Customer.java"

    def test_no_protected_names_allows_all(self):
        """Without protected_names, all valid filenames are allowed."""
        assert PathValidator.validate_artifact_path("session.json") == "session.json"
        assert PathValidator.validate_artifact_path("config.yml") == "config.yml"


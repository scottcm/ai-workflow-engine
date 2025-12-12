"""
Path validation utilities for AI Workflow Engine.

Provides shared security validation for:
- Entity name sanitization
- Path traversal prevention
- Environment variable expansion
- File existence validation

Used by profiles to ensure safe user inputs and file operations.
"""

import os
import re
from pathlib import Path
from typing import Any


class PathValidationError(Exception):
    """Raised when path validation fails."""
    pass


class PathValidator:
    """Validates and sanitizes file paths and names."""
    
    # Allowed characters in entity names and path components
    SAFE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    
    # Template variable pattern
    TEMPLATE_VAR_PATTERN = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
    
    @classmethod
    def sanitize_entity_name(cls, entity: str) -> str:
        """
        Sanitize entity name to prevent path traversal and injection.
        
        Args:
            entity: Raw entity name from user input
            
        Returns:
            Sanitized entity name
            
        Raises:
            PathValidationError: If entity name contains invalid characters
            
        Examples:
            >>> PathValidator.sanitize_entity_name("Product")
            'Product'
            >>> PathValidator.sanitize_entity_name("../../../etc/passwd")
            PathValidationError: Invalid entity name
        """
        if not entity:
            raise PathValidationError("Entity name cannot be empty")
        
        if not cls.SAFE_NAME_PATTERN.match(entity):
            raise PathValidationError(
                f"Invalid entity name: '{entity}'. "
                f"Only alphanumeric characters, hyphens, and underscores allowed."
            )
        
        # Additional check: no path separators
        if '/' in entity or '\\' in entity or '..' in entity:
            raise PathValidationError(
                f"Invalid entity name: '{entity}'. "
                f"Path separators and '..' not allowed."
            )
        
        return entity
    
    @classmethod
    def sanitize_path_component(cls, component: str) -> str:
        """
        Sanitize a single path component (directory or filename).
        
        Args:
            component: Raw path component
            
        Returns:
            Sanitized component
            
        Raises:
            PathValidationError: If component contains invalid characters
        """
        if not component:
            raise PathValidationError("Path component cannot be empty")
        
        if not cls.SAFE_NAME_PATTERN.match(component):
            raise PathValidationError(
                f"Invalid path component: '{component}'. "
                f"Only alphanumeric characters, hyphens, and underscores allowed."
            )
        
        return component
    
    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """
        Sanitize a filename for safe file writing.
        
        Args:
            filename: Filename to validate (e.g., "Product.java")
            
        Returns:
            Sanitized filename (unchanged if valid)
            
        Raises:
            PathValidationError: If filename is invalid
            
        Examples:
            >>> PathValidator.sanitize_filename("Product.java")
            'Product.java'
            
            >>> PathValidator.sanitize_filename("../File.java")
            PathValidationError: Invalid filename
        """
        if not filename:
            raise PathValidationError("Filename cannot be empty")
            
        if '/' in filename or '\\' in filename:
            raise PathValidationError(f"Invalid filename: '{filename}'. Path separators not allowed.")
            
        if '..' in filename:
            raise PathValidationError(f"Invalid filename: '{filename}'. Parent directory references not allowed.")
            
        if filename.startswith('.'):
            raise PathValidationError(f"Invalid filename: '{filename}'. Hidden files or dot-only names not allowed.")
            
        # Split into name and extension parts
        # "Product.java" -> "Product", ".java"
        # "Test.spec.java" -> "Test.spec", ".java" - wait, requirements say:
        # "Name part = everything before the last dot"
        # "Extension is allowed to contain dots (e.g., "file.test.java" is valid if "file" passes)" 
        # Actually, looking at requirements again: "Name part = everything before the last dot" usually implies extension is the last part.
        # But looking at example "file.test.java" valid if "file" passes suggests we might split on FIRST dot?
        # Let's re-read carefully: "Extension is allowed to contain dots... file.test.java is valid if file passes".
        # This implies we split at the FIRST dot. 
        # "Name part" (to check against SAFE_NAME_PATTERN) is the first segment.
        
        parts = filename.split('.', 1)
        name_part = parts[0]
        
        if not cls.SAFE_NAME_PATTERN.match(name_part):
             raise PathValidationError(
                f"Invalid filename format: '{filename}'. "
                f"Name part '{name_part}' must contain only alphanumeric characters, hyphens, and underscores."
            )
            
        return filename

    @classmethod
    def expand_env_vars(cls, path: str) -> str:
        """
        Safely expand environment variables in path.
        
        Args:
            path: Path string with potential ${VAR} references
            
        Returns:
            Expanded path string
            
        Raises:
            PathValidationError: If environment variable is undefined
            
        Examples:
            >>> os.environ['STANDARDS_DIR'] = '/path/to/standards'
            >>> PathValidator.expand_env_vars("${STANDARDS_DIR}/file.md")
            '/path/to/standards/file.md'
        """
        # Find all ${VAR} patterns
        vars_needed = set(re.findall(r'\$\{([^}]+)\}', path))
        
        # Check all are defined
        undefined = [v for v in vars_needed if v not in os.environ]
        if undefined:
            raise PathValidationError(
                f"Undefined environment variables: {', '.join(undefined)}"
            )
        
        # Expand using os.path.expandvars
        expanded = os.path.expandvars(path)
        
        return expanded
    
    @classmethod
    def validate_absolute_path(cls, path: str | Path, must_exist: bool = True) -> Path:
        """
        Validate and resolve path to absolute form.
        
        Relative paths are resolved relative to current working directory.
        
        Args:
            path: Path to validate (absolute or relative)
            must_exist: If True, path must exist
            
        Returns:
            Resolved absolute Path object
            
        Raises:
            PathValidationError: If validation fails
            
        Examples:
            >>> PathValidator.validate_absolute_path("/absolute/path")
            Path('/absolute/path')
            
            >>> PathValidator.validate_absolute_path("./relative/path")
            Path('/current/working/directory/relative/path')
        """
        # Expand environment variables first
        if isinstance(path, str):
            path = cls.expand_env_vars(path)
        
        # Resolve to absolute (handles both absolute and relative)
        path_obj = Path(path).resolve()
        
        if must_exist and not path_obj.exists():
            raise PathValidationError(
                f"Path does not exist: {path_obj}"
            )
        
        return path_obj
    
    @classmethod
    def validate_directory(cls, path: str | Path, must_exist: bool = True) -> Path:
        """
        Validate that path is a directory.
        
        Args:
            path: Path to validate
            must_exist: If True, directory must exist
            
        Returns:
            Resolved absolute Path object
            
        Raises:
            PathValidationError: If validation fails
        """
        path_obj = cls.validate_absolute_path(path, must_exist=must_exist)
        
        if must_exist and not path_obj.is_dir():
            raise PathValidationError(
                f"Path is not a directory: {path_obj}"
            )
        
        return path_obj
    
    @classmethod
    def validate_file(cls, path: str | Path, must_exist: bool = True) -> Path:
        """
        Validate that path is a file.
        
        Args:
            path: Path to validate
            must_exist: If True, file must exist
            
        Returns:
            Resolved absolute Path object
            
        Raises:
            PathValidationError: If validation fails
        """
        path_obj = cls.validate_absolute_path(path, must_exist=must_exist)
        
        if must_exist and not path_obj.is_file():
            raise PathValidationError(
                f"Path is not a file: {path_obj}"
            )
        
        return path_obj
    
    @classmethod
    def validate_within_root(cls, file_path: Path, root: Path) -> Path:
        """
        Validate that file_path is within root directory (no path traversal).
        
        Args:
            file_path: File path to validate
            root: Root directory that must contain file_path
            
        Returns:
            Validated file path
            
        Raises:
            PathValidationError: If file_path escapes root directory
            
        Examples:
            >>> root = Path("/home/user/standards")
            >>> PathValidator.validate_within_root(
            ...     Path("/home/user/standards/JPA.md"), root
            ... )
            Path('/home/user/standards/JPA.md')
            
            >>> PathValidator.validate_within_root(
            ...     Path("/etc/passwd"), root
            ... )
            PathValidationError: Path traversal detected
        """
        try:
            # Resolve both to absolute paths
            file_resolved = file_path.resolve()
            root_resolved = root.resolve()
            
            # Check if file is relative to root
            file_resolved.relative_to(root_resolved)
            
            return file_resolved
            
        except ValueError:
            raise PathValidationError(
                f"Path traversal detected: {file_path} is not within {root}"
            )
    
    @classmethod
    def validate_template_variables(
        cls,
        template: str,
        allowed_vars: set[str]
    ) -> set[str]:
        """
        Validate template string contains only allowed variables.
        
        Args:
            template: Template string like "{entity}/{scope}"
            allowed_vars: Set of allowed variable names
            
        Returns:
            Set of variables found in template
            
        Raises:
            PathValidationError: If template contains invalid variables
            
        Examples:
            >>> PathValidator.validate_template_variables(
            ...     "{entity}/{scope}",
            ...     {"entity", "scope", "timestamp"}
            ... )
            {'entity', 'scope'}
        """
        found_vars = set(cls.TEMPLATE_VAR_PATTERN.findall(template))
        
        invalid_vars = found_vars - allowed_vars
        if invalid_vars:
            raise PathValidationError(
                f"Invalid template variables: {invalid_vars}. "
                f"Allowed: {allowed_vars}"
            )
        
        return found_vars
    
    @classmethod
    def validate_template_has_required(
        cls,
        template: str,
        required_vars: set[str]
    ) -> None:
        """
        Validate template contains required variables.
        
        Args:
            template: Template string to validate
            required_vars: Variables that must appear in template
            
        Raises:
            PathValidationError: If required variables are missing
            
        Examples:
            >>> PathValidator.validate_template_has_required(
            ...     "{scope}/{entity}",
            ...     {"entity"}
            ... )
            # Passes
            
            >>> PathValidator.validate_template_has_required(
            ...     "{scope}",
            ...     {"entity"}
            ... )
            PathValidationError: Template missing required variables
        """
        found_vars = set(cls.TEMPLATE_VAR_PATTERN.findall(template))
        
        missing_vars = required_vars - found_vars
        if missing_vars:
            raise PathValidationError(
                f"Template missing required variables: {missing_vars}"
            )
    
    @classmethod
    def format_template(
        cls,
        template: str,
        variables: dict[str, Any],
        sanitize: bool = True
    ) -> str:
        """
        Format template string with validated variables.
        
        Args:
            template: Template string like "{entity}/{scope}"
            variables: Variable values to substitute
            sanitize: If True, sanitize variable values
            
        Returns:
            Formatted string with variables substituted
            
        Raises:
            PathValidationError: If variables are invalid
            
        Examples:
            >>> PathValidator.format_template(
            ...     "{entity}/{scope}",
            ...     {"entity": "Product", "scope": "domain"}
            ... )
            'Product/domain'
        """
        # Validate all template variables are provided
        template_vars = set(cls.TEMPLATE_VAR_PATTERN.findall(template))
        missing = template_vars - set(variables.keys())
        if missing:
            raise PathValidationError(
                f"Missing template variables: {missing}"
            )
        
        # Sanitize variable values if requested
        if sanitize:
            sanitized = {}
            for key, value in variables.items():
                if key in template_vars:
                    sanitized[key] = cls.sanitize_path_component(str(value))
                else:
                    sanitized[key] = value
            variables = sanitized
        
        # Format template
        try:
            return template.format(**variables)
        except KeyError as e:
            raise PathValidationError(f"Template formatting failed: {e}")


# Convenience functions for common validations

def sanitize_entity_name(entity: str) -> str:
    """Sanitize entity name - convenience wrapper."""
    return PathValidator.sanitize_entity_name(entity)


def validate_standards_root(path: str) -> Path:
    """Validate standards root directory exists and is accessible."""
    return PathValidator.validate_directory(path, must_exist=True)


def validate_target_root(path: str | None) -> Path | None:
    """Validate target root directory (optional)."""
    if path is None:
        return None
    return PathValidator.validate_directory(path, must_exist=False)


def validate_standards_file(
    filename: str,
    standards_root: Path
) -> Path:
    """
    Validate standards file exists within standards root.
    
    Args:
        filename: Relative filename (e.g., "JPA_AND_DATABASE.md")
        standards_root: Root directory for standards
        
    Returns:
        Absolute path to standards file
        
    Raises:
        PathValidationError: If file doesn't exist or escapes root
    """
    file_path = standards_root / filename
    
    # Check for path traversal
    PathValidator.validate_within_root(file_path, standards_root)
    
    # Check file exists
    if not file_path.exists():
        raise PathValidationError(
            f"Standards file not found: {file_path}"
        )
    
    if not file_path.is_file():
        raise PathValidationError(
            f"Not a file: {file_path}"
        )
    
    return file_path

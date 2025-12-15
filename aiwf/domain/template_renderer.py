"""Generic template rendering utilities for workflow profiles.

This module is intentionally profile-agnostic. Profiles may use it to merge layered
templates (via {{include: ...}} directives) and perform placeholder substitution
(via {{KEY}} tokens), but profiles are not required to use it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re


_INCLUDE_RE = re.compile(r"\{\{\s*include:\s*([^}]+?)\s*\}\}")
# Match {{KEY}} placeholders, but do not match include directives.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(?!include:)([A-Za-z0-9_]+)\s*\}\}")


def render_template(
    template_path: Path,
    context: dict[str, Any],
    templates_root: Path | None = None,
) -> str:
    """Render a template by resolving includes and filling placeholders.

    Args:
        template_path: Path to template file.
        context: Variables for placeholder substitution.
        templates_root: Optional root for resolving include paths. If provided,
            relative include paths are resolved against this root; otherwise they
            are resolved relative to the including file.

    Returns:
        Rendered template content.

    Raises:
        FileNotFoundError: If template or included file missing.
        KeyError: If required context variable missing.
        RuntimeError: If circular includes detected.
    """
    resolved = resolve_includes(template_path, templates_root=templates_root, visited=None)
    return fill_placeholders(resolved, context)


def resolve_includes(
    template_path: Path,
    templates_root: Path | None = None,
    visited: set[Path] | None = None,
) -> str:
    """Recursively resolve {{include: ...}} directives.

    Include resolution rules:
    - If templates_root is provided, relative includes resolve against it.
    - Otherwise, relative includes resolve against the directory of the including file.
    - Absolute include paths are used as-is.

    Args:
        template_path: Path to template file.
        templates_root: Root directory for relative includes.
        visited: Set of already-visited paths (circular detection).

    Returns:
        Template content with all includes resolved.

    Raises:
        FileNotFoundError: If template or included file missing.
        RuntimeError: If circular includes detected.
    """
    visited = visited or set()

    # Use a stable key for cycle detection.
    key = template_path.resolve()
    if key in visited:
        raise RuntimeError(f"Circular include detected: {template_path}")
    visited.add(key)

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    content = template_path.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        include_rel = Path(raw)

        if include_rel.is_absolute():
            include_path = include_rel
        else:
            base = templates_root if templates_root is not None else template_path.parent
            include_path = base / include_rel

        include_path = include_path.resolve()

        if not include_path.exists():
            raise FileNotFoundError(f"Included template not found: {include_path}")

        # Pass the same templates_root and the same visited set.
        return resolve_includes(include_path, templates_root=templates_root, visited=visited)

    # Replace all include directives. Recursion handles nesting.
    rendered = _INCLUDE_RE.sub(_replace, content)
    return rendered


def fill_placeholders(content: str, context: dict[str, Any]) -> str:
    """Replace {{PLACEHOLDER}} with context values.

    Placeholders are case-sensitive. Include directives are not treated as placeholders.

    Args:
        content: Template content with placeholders.
        context: Substitution variables.

    Returns:
        Content with placeholders filled.

    Raises:
        KeyError: If required placeholder not in context.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(key)
        value = context.get(key)
        return "" if value is None else str(value)

    return _PLACEHOLDER_RE.sub(_replace, content)

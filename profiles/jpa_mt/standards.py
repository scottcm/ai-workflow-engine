"""YAML Rules-based Standards Provider for JPA-MT Profile.

Reads YAML rules files and produces a markdown standards bundle
filtered by scope.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

from aiwf.domain.errors import ProviderError


class JpaMtStandardsProvider:
    """Standards provider that reads YAML rules files.

    Parses YAML files with hierarchical rule definitions and produces
    a markdown standards bundle filtered by scope.

    Config structure:
        {
            "rules_path": "/path/to/rules"  # Directory containing *.rules.yml files
        }
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize provider with configuration.

        Args:
            config: Configuration dict with:
                - rules_path: Path to directory containing *.rules.yml files
        """
        self.config = config
        rules_path = config.get("rules_path", "")
        self.rules_path = Path(rules_path) if rules_path else None

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with provider metadata
        """
        return {
            "name": "yaml-rules",
            "description": "YAML rules-based standards provider for JPA-MT",
            "requires_config": True,
            "config_keys": ["rules_path"],
            "default_connection_timeout": None,  # Local filesystem, no connection phase
            "default_response_timeout": 10,  # Seconds to read all YAML files
        }

    def validate(self) -> None:
        """Verify rules path exists and contains rules files.

        Raises:
            ProviderError: If rules_path is not configured or doesn't exist
        """
        if not self.rules_path:
            raise ProviderError("rules_path not configured")

        if not self.rules_path.exists():
            raise ProviderError(f"Rules path not found: {self.rules_path}")

        if not self.rules_path.is_dir():
            raise ProviderError(f"Rules path is not a directory: {self.rules_path}")

        # Check for at least one rules file
        rules_files = list(self.rules_path.glob("*.rules.yml"))
        if not rules_files:
            raise ProviderError(f"No *.rules.yml files found in {self.rules_path}")

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Create standards bundle filtered by scope.

        Args:
            context: Workflow context with:
                - scope: Scope name (for header)
                - standards_files: List of file names to load
                - standards_prefixes: List of rule ID prefixes to include (empty = all)
            connection_timeout: Ignored (filesystem provider)
            response_timeout: Ignored for simplicity (fast local reads)

        Returns:
            Markdown-formatted standards bundle

        Raises:
            ProviderError: If bundle creation fails or rules_path not configured
            ValueError: If required context fields missing
        """
        # Guard: ensure rules_path is configured before loading
        if not self.rules_path:
            raise ProviderError(
                "rules_path not configured. Call validate() first or check configuration."
            )

        scope = context.get("scope") if isinstance(context, dict) else None
        standards_files = context.get("standards_files", [])
        standards_prefixes = context.get("standards_prefixes", [])

        if not scope:
            raise ValueError("scope is required in context")

        # Load rules from specified files only
        all_rules = self._load_rules(standards_files)

        # Filter by prefixes
        filtered_rules = self._filter_by_prefixes(all_rules, standards_prefixes)

        # Format as markdown
        return self._format_bundle(filtered_rules, scope)

    def _load_rules(
        self, file_names: list[str]
    ) -> dict[str, list[tuple[str, str, str]]]:
        """Load rules from specified YAML files.

        Args:
            file_names: List of file names to load (relative to rules_path)

        Detects and warns about duplicate rule IDs across files.

        Returns:
            Dict mapping category names to list of (rule_id, severity, text) tuples
        """
        if not self.rules_path:
            return {}

        rules_by_category: dict[str, list[tuple[str, str, str]]] = {}
        seen_rule_ids: dict[str, str] = {}  # rule_id -> first file where seen

        # If no files specified, load all *.rules.yml (backward compatibility)
        if not file_names:
            rules_files = sorted(self.rules_path.glob("*.rules.yml"))
        else:
            rules_files = [self.rules_path / name for name in file_names]

        for file_path in rules_files:
            if not file_path.exists():
                logger.warning("Standards file not found: %s", file_path)
                continue
            try:
                category_name = self._file_to_category(file_path)
                file_rules = self._parse_yaml_file(file_path)
                if file_rules:
                    # Check for duplicate rule IDs
                    for rule_id, severity, text in file_rules:
                        if rule_id in seen_rule_ids:
                            logger.warning(
                                "Duplicate rule ID '%s' found in %s "
                                "(first seen in %s). Last definition wins.",
                                rule_id,
                                file_path.name,
                                seen_rule_ids[rule_id],
                            )
                        seen_rule_ids[rule_id] = file_path.name

                    rules_by_category[category_name] = file_rules
            except yaml.YAMLError as e:
                raise ProviderError(f"Failed to parse {file_path}: {e}")
            except OSError as e:
                raise ProviderError(f"Failed to read {file_path}: {e}")

        return rules_by_category

    # Known acronyms that should remain uppercase after title() transformation
    KNOWN_ACRONYMS = ["JPA", "API", "DTO", "REST", "SQL", "CRUD", "HTTP", "JSON", "XML"]

    def _file_to_category(self, file_path: Path) -> str:
        """Convert file name to human-readable category name.

        Args:
            file_path: Path to rules file

        Returns:
            Category name (e.g., "JPA and Database Standards")
        """
        # Remove suffix and convert to title case
        name = file_path.stem  # e.g., "JPA_AND_DATABASE-marked.rules"
        name = name.replace(".rules", "")  # Remove .rules if present
        name = name.replace("-marked", "")  # Remove -marked suffix
        name = name.replace("_", " ").title()  # Convert to title case

        # Restore known acronyms to uppercase
        for acronym in self.KNOWN_ACRONYMS:
            # Replace title-cased version with uppercase
            title_version = acronym.title()  # e.g., "Jpa"
            name = name.replace(title_version, acronym)

        return f"{name} Standards"

    def _parse_yaml_file(self, file_path: Path) -> list[tuple[str, str, str]]:
        """Parse a single YAML rules file.

        Args:
            file_path: Path to YAML file

        Returns:
            List of (rule_id, severity, text) tuples
        """
        content = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data or not isinstance(data, dict):
            return []

        rules: list[tuple[str, str, str]] = []
        self._extract_rules(data, rules)
        return rules

    def _extract_rules(
        self, data: dict[str, Any], rules: list[tuple[str, str, str]]
    ) -> None:
        """Recursively extract rules from nested YAML structure.

        Args:
            data: YAML data (nested dicts)
            rules: List to append rules to (modified in place)
        """
        for key, value in data.items():
            if isinstance(value, dict):
                # Check if this is a rules dict (keys look like rule IDs)
                # Rule IDs have format: PREFIX-CODE-NNN
                sample_key = next(iter(value.keys()), "")
                if self._is_rule_id(sample_key):
                    # This is a rules dict
                    for rule_id, rule_text in value.items():
                        if isinstance(rule_text, str):
                            severity, text = self._parse_rule_text(rule_text)
                            rules.append((rule_id, severity, text))
                else:
                    # Recurse into nested structure
                    self._extract_rules(value, rules)

    def _is_rule_id(self, key: str) -> bool:
        """Check if a string looks like a rule ID.

        Rule IDs have format like JPA-ENT-001, JV-DI-001, etc.

        Args:
            key: String to check

        Returns:
            True if key looks like a rule ID
        """
        if not key or "-" not in key:
            return False
        # Rule IDs typically have 2-3 parts separated by hyphens
        # and end with digits
        parts = key.split("-")
        if len(parts) < 2:
            return False
        # Last part should be numeric (or mostly numeric)
        last_part = parts[-1]
        return any(c.isdigit() for c in last_part)

    def _parse_rule_text(self, text: str) -> tuple[str, str]:
        """Parse rule text to extract severity and description.

        Format: "{severity}: {description}"
        Severity: C (Critical), M (Major), m (minor)

        Args:
            text: Raw rule text

        Returns:
            Tuple of (severity, description)
        """
        if ": " in text:
            severity_char, description = text.split(": ", 1)
            severity_char = severity_char.strip()
            if severity_char in ("C", "M", "m"):
                return severity_char, description.strip()
        # Default to no severity if format doesn't match
        return "", text

    def _filter_by_prefixes(
        self,
        rules_by_category: dict[str, list[tuple[str, str, str]]],
        prefixes: list[str],
    ) -> dict[str, list[tuple[str, str, str]]]:
        """Filter rules by ID prefixes.

        Args:
            rules_by_category: All rules grouped by category
            prefixes: List of rule ID prefixes to include (empty = all)

        Returns:
            Filtered rules dict
        """
        # Empty prefixes means include all
        if not prefixes:
            return rules_by_category

        filtered: dict[str, list[tuple[str, str, str]]] = {}
        for category, rules in rules_by_category.items():
            matching_rules = [
                (rule_id, severity, text)
                for rule_id, severity, text in rules
                if any(rule_id.startswith(prefix) for prefix in prefixes)
            ]
            if matching_rules:
                filtered[category] = matching_rules

        return filtered

    def _format_bundle(
        self, rules_by_category: dict[str, list[tuple[str, str, str]]], scope: str
    ) -> str:
        """Format rules as markdown bundle.

        Args:
            rules_by_category: Rules grouped by category
            scope: Scope name for header

        Returns:
            Markdown-formatted standards bundle
        """
        lines = [f"# Standards Bundle ({scope} scope)", ""]

        for category, rules in rules_by_category.items():
            lines.append(f"## {category}")
            lines.append("")

            for rule_id, severity, text in rules:
                if severity:
                    lines.append(f"- **{rule_id}** ({severity}): {text}")
                else:
                    lines.append(f"- **{rule_id}**: {text}")

            lines.append("")

        return "\n".join(lines)

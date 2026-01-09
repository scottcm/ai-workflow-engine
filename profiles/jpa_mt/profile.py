"""JPA-MT Profile Implementation (v2).

Multi-tenant JPA code generation for Spring/Hibernate environments.
"""

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from aiwf.domain.providers.ai_provider import AIProvider

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.models.write_plan import WritePlan, WriteOp
from aiwf.domain.profiles.workflow_profile import PromptResult, WorkflowProfile

from .config import JpaMtConfig
from .review_metadata import ParseError, ReviewVerdict, format_review_summary, parse_review_metadata
from .standards import JpaMtStandardsProvider

# Register the standards provider with the factory
from aiwf.domain.standards import StandardsProviderFactory
StandardsProviderFactory.register("yaml-rules", JpaMtStandardsProvider)

logger = logging.getLogger(__name__)


class JpaMtProfile(WorkflowProfile):
    """Multi-tenant JPA domain layer generation profile (v2)."""

    def __init__(self, config: JpaMtConfig | None = None):
        """Initialize profile with optional config.

        Args:
            config: Profile configuration. If None, auto-loads config.yml from
                   profile directory (if exists) or uses default JpaMtConfig.
        """
        if config is not None:
            self.config = config
        else:
            # Auto-load config.yml from profile directory if it exists
            config_path = Path(__file__).parent / "config.yml"
            if config_path.exists():
                self.config = JpaMtConfig.from_yaml(config_path)
            else:
                self.config = JpaMtConfig()
        self._ai_provider: "AIProvider | None" = None  # Lazy cache for ADR-0010

    @classmethod
    def from_config_file(cls, config_path: Path | str | None = None) -> "JpaMtProfile":
        """Factory method to create profile from config file.

        This is the preferred way to create a profile when loading
        from a YAML configuration file.

        Args:
            config_path: Path to config.yml file. If None, looks for
                        config.yml in profile directory.

        Returns:
            JpaMtProfile instance with loaded configuration.

        Raises:
            FileNotFoundError: If config file doesn't exist and path was explicit.

        Example:
            # Load from default location
            profile = JpaMtProfile.from_config_file()

            # Load from specific path
            profile = JpaMtProfile.from_config_file("/path/to/config.yml")
        """
        if config_path is None:
            # Default to profile directory's config.yml
            config_path = Path(__file__).parent / "config.yml"
            if not config_path.exists():
                # No default config file, use default config
                return cls()
        else:
            config_path = Path(config_path)
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")

        config = JpaMtConfig.from_yaml(config_path)
        return cls(config=config)

    @property
    def ai_provider(self) -> "AIProvider | None":
        """Get the configured AI provider, if any.

        Lazy initialization pattern (ADR-0010): Provider is created on first
        access and cached for reuse. Returns None if no ai_provider configured.

        For testing, inject mock directly via self._ai_provider = mock.

        Raises:
            ValueError: If ai_provider is 'manual' (can't generate content)
            KeyError: If ai_provider key is not registered
        """
        if self._ai_provider is None and self.config.ai_provider:
            if self.config.ai_provider == "manual":
                raise ValueError(
                    "Cannot use 'manual' as profile ai_provider. "
                    "'manual' means no AI - use a real provider like 'claude-code'."
                )
            from aiwf.domain.providers.provider_factory import AIProviderFactory
            self._ai_provider = AIProviderFactory.create(self.config.ai_provider)
        return self._ai_provider

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "jpa-mt",
            "description": "Multi-tenant JPA domain layer generation (v2)",
            "target_stack": "Java/Spring/Hibernate/PostgreSQL",
            "scopes": ["domain", "service", "api", "full"],
            "phases": ["planning", "generation", "review", "revision"],
            "requires_config": False,
            "config_keys": ["base_package", "standards", "scopes"],
            "context_schema": {
                "entity": {"type": "string", "required": True},
                "table": {"type": "string", "required": True},
                "bounded_context": {"type": "string", "required": True},
                "scope": {
                    "type": "string",
                    "required": False,
                    "default": "domain",
                    "choices": ["domain", "service", "api", "full"],
                },
                "schema_file": {"type": "path", "required": True, "exists": True},
                "design": {"type": "path", "required": False, "exists": True},
            },
            "can_regenerate_prompts": True,
        }

    def get_default_standards_provider_key(self) -> str:
        return "yaml-rules"  # New provider for YAML-based standards

    def get_standards_config(self) -> dict[str, Any]:
        """Get standards provider configuration.

        Resolution order:
        1. First source in standards.sources (if configured)
        2. standards.default_rules_path (if configured)
        3. Profile default: {profile_dir}/rules/ (if exists)

        Returns:
            Dict with 'rules_path' key for JpaMtStandardsProvider
        """
        rules_path = None

        # 1. Check explicit sources first
        if self.config.standards.sources:
            rules_path = self.config.standards.sources[0].path

        # 2. Fall back to configured default_rules_path
        if not rules_path and self.config.standards.default_rules_path:
            rules_path = self.config.standards.default_rules_path

        # 3. Fall back to profile default location
        if not rules_path:
            profile_rules = Path(__file__).parent / "rules"
            if profile_rules.exists():
                rules_path = str(profile_rules)

        return {"rules_path": rules_path}

    # =========================================================================
    # CONVENTION SYSTEM
    # =========================================================================

    def _load_conventions(self, convention_name: str, context: dict) -> dict[str, str]:
        """Load convention variables from conventions.json.

        Resolution order:
        1. Project directory: {working_dir}/.aiwf/jpa-mt/conventions.json
        2. Profile defaults: profiles/jpa_mt/conventions.json
        3. Sample conventions: docs/samples/conventions.json

        Args:
            convention_name: Name of the convention set (e.g., "control-plane")
            context: Workflow context (may contain "working_dir")

        Returns:
            Flattened dict of convention variables

        Raises:
            FileNotFoundError: If conventions.json not found
            KeyError: If convention_name not found in file
        """
        working_dir = Path(context.get("working_dir", ".")).resolve()

        # Resolution order for conventions.json
        search_paths = [
            working_dir / ".aiwf" / "jpa-mt" / "conventions.json",
            Path(__file__).parent / "conventions.json",
            Path(__file__).parent.parent.parent / "docs" / "samples" / "conventions.json",
        ]

        conventions_data = None
        for path in search_paths:
            if path.exists():
                logger.debug("Loading conventions from: %s", path)
                with open(path, encoding="utf-8") as f:
                    conventions_data = json.load(f)
                break

        if conventions_data is None:
            raise FileNotFoundError(
                f"conventions.json not found.\n"
                f"Searched:\n" +
                "\n".join(f"  - {p}" for p in search_paths)
            )

        if convention_name not in conventions_data:
            available = list(conventions_data.keys())
            raise KeyError(
                f"Convention '{convention_name}' not found.\n"
                f"Available: {available}"
            )

        return self._flatten_conventions(conventions_data[convention_name])

    def _flatten_conventions(self, nested: dict) -> dict[str, str]:
        """Flatten nested convention dict into single-level dict.

        Converts:
            {"naming": {"entity_class": "Foo"}, "packages": {"base": "com.x"}}
        Into:
            {"entity_class": "Foo", "base": "com.x"}

        Skips keys starting with "_" (like "_comment").

        Args:
            nested: Nested convention dict

        Returns:
            Flattened dict with all variables at top level
        """
        result: dict[str, str] = {}
        for section_name, section in nested.items():
            if section_name.startswith("_"):
                continue  # Skip comment fields
            if isinstance(section, dict):
                for key, value in section.items():
                    if key.startswith("_"):
                        continue  # Skip comment fields
                    # Convert lists to comma-separated strings
                    if isinstance(value, list):
                        result[key] = ", ".join(str(v) for v in value)
                    else:
                        result[key] = str(value)
        return result

    def _process_conditionals(
        self,
        text: str,
        variables: dict[str, str],
    ) -> str:
        """Process conditional blocks in templates.

        Supports simple conditional syntax:
        - {{#if var}}content{{/if}} - include if var is defined and non-empty
        - {{#unless var}}content{{/unless}} - include if var is undefined or empty

        Conditionals can be nested. Processing is done iteratively from
        innermost to outermost by matching only blocks that don't contain
        other conditional markers inside.

        Args:
            text: Text with conditional blocks
            variables: Dict of variable name -> value

        Returns:
            Text with conditionals resolved
        """
        # Match innermost {{#if var}}...{{/if}} blocks (no nested conditionals inside)
        # The negative lookahead (?:(?!\{\{#).)* ensures no {{# inside content
        if_pattern = re.compile(
            r"\{\{#if\s+(\w+)\}\}((?:(?!\{\{#)(?!\{\{/).)*)?\{\{/if\}\}",
            re.DOTALL
        )

        # Match innermost {{#unless var}}...{{/unless}} blocks
        unless_pattern = re.compile(
            r"\{\{#unless\s+(\w+)\}\}((?:(?!\{\{#)(?!\{\{/).)*)?\{\{/unless\}\}",
            re.DOTALL
        )

        # Iterate until no more conditionals (handles nesting)
        max_iterations = 10
        for _ in range(max_iterations):
            # Process #if blocks
            def if_replace(match: re.Match) -> str:
                var_name = match.group(1)
                content = match.group(2) or ""
                value = variables.get(var_name, "")
                return content if value else ""

            new_text = if_pattern.sub(if_replace, text)

            # Process #unless blocks
            def unless_replace(match: re.Match) -> str:
                var_name = match.group(1)
                content = match.group(2) or ""
                value = variables.get(var_name, "")
                return content if not value else ""

            new_text = unless_pattern.sub(unless_replace, new_text)

            if new_text == text:
                break
            text = new_text

        return text

    def _resolve_variables(
        self,
        text: str,
        variables: dict[str, str],
        max_passes: int = 3,
    ) -> str:
        """Multi-pass variable substitution with conditional support.

        First processes conditional blocks ({{#if}}/{{#unless}}), then
        repeatedly substitutes {{var}} placeholders until no more remain
        or max_passes is reached.

        Unknown variables are preserved as-is (placeholder remains in output).
        This allows engine-owned variables like {{STANDARDS}} to pass through
        for later resolution by PromptAssembler.

        Args:
            text: Text with {{var}} placeholders and optional conditionals
            variables: Dict of variable name -> value
            max_passes: Maximum substitution passes (default: 3)

        Returns:
            Text with conditionals resolved and variables substituted
        """
        # First, process conditionals
        text = self._process_conditionals(text, variables)

        # Then, substitute variables
        pattern = re.compile(r"\{\{(\w+)\}\}")

        for pass_num in range(max_passes):
            def replace(match: re.Match) -> str:
                key = match.group(1)
                # Preserve unknown variables as placeholders for engine to resolve
                # (or to surface as errors if truly undefined)
                return variables.get(key, match.group(0))

            new_text = pattern.sub(replace, text)
            if new_text == text:
                # No changes made, stop early
                break
            text = new_text

        return text

    def _build_variables(
        self,
        context: dict,
        convention_name: str | None = None,
    ) -> dict[str, str]:
        """Build complete variable dict from context and conventions.

        Merges:
        1. Convention variables (from conventions.json)
        2. Context variables (entity, table, bounded_context, scope, etc.)

        Context variables take precedence over conventions.

        Args:
            context: Workflow context dict
            convention_name: Optional convention set name

        Returns:
            Merged variable dict ready for substitution
        """
        variables: dict[str, str] = {}

        # Load convention variables if specified
        if convention_name:
            try:
                variables = self._load_conventions(convention_name, context)
            except (FileNotFoundError, KeyError) as e:
                logger.warning("Failed to load conventions: %s", e)

        # Add context variables (these take precedence)
        context_vars = {
            "entity": context.get("entity", ""),
            "table": context.get("table", ""),
            "bounded_context": context.get("bounded_context", ""),
            "scope": context.get("scope", "domain"),
            "schema_file": context.get("schema_file", ""),
            "iteration": str(context.get("iteration", 1)),
        }

        # Add artifacts if present in context
        if "artifacts" in context:
            context_vars["artifacts"] = context["artifacts"]

        variables.update(context_vars)
        return variables

    # =========================================================================
    # TEMPLATE RESOLUTION
    # =========================================================================

    def _resolve_template_path(self, name: str, context: dict) -> Path:
        """Resolve template path with project override support.

        Resolution order:
        1. Project directory: {working_dir}/.aiwf/jpa-mt/templates/{name}
        2. Profile defaults: profiles/jpa_mt/templates/{name}

        Args:
            name: Template filename (e.g., "planning-prompt.md")
            context: Workflow context (may contain "working_dir")

        Returns:
            Path to the template file

        Raises:
            FileNotFoundError: If template not found in any location
        """
        # Get working directory from context or use current directory
        working_dir = Path(context.get("working_dir", ".")).resolve()

        # Check project override first
        project_path = working_dir / ".aiwf" / "jpa-mt" / "templates" / name
        if project_path.exists():
            logger.debug("Using project template: %s", project_path)
            return project_path

        # Fall back to profile defaults
        profile_path = Path(__file__).parent / "templates" / name
        if profile_path.exists():
            logger.debug("Using profile template: %s", profile_path)
            return profile_path

        raise FileNotFoundError(
            f"Template not found: {name}\n"
            f"Searched:\n"
            f"  - {project_path}\n"
            f"  - {profile_path}"
        )

    def _load_template(
        self,
        name: str,
        context: dict,
        extra_vars: dict[str, str] | None = None,
    ) -> str:
        """Load and resolve a template file.

        Loads the template from disk and substitutes placeholders with
        values from context and extra_vars. Placeholders use {{name}} syntax.

        Args:
            name: Template filename (e.g., "planning-prompt.md")
            context: Workflow context dict with entity, table, etc.
            extra_vars: Additional variables (e.g., artifacts, standards)

        Returns:
            Fully resolved template string

        Raises:
            FileNotFoundError: If template not found
        """
        template_path = self._resolve_template_path(name, context)
        content = template_path.read_text(encoding="utf-8")

        # Build substitution dict from context
        substitutions: dict[str, str] = {
            "entity": context.get("entity", ""),
            "table": context.get("table", ""),
            "bounded_context": context.get("bounded_context", ""),
            "scope": context.get("scope", "domain"),
            "schema_file": context.get("schema_file", ""),
        }

        # Add extra variables (artifacts, standards, etc.)
        if extra_vars:
            substitutions.update(extra_vars)

        # Substitute placeholders using regex for {{name}} pattern
        def replace_placeholder(match: re.Match) -> str:
            key = match.group(1)
            if key in substitutions:
                return substitutions[key]
            # Leave unrecognized placeholders as-is
            logger.debug("Unrecognized placeholder: {{%s}}", key)
            return match.group(0)

        resolved = re.sub(r"\{\{(\w+)\}\}", replace_placeholder, content)
        return resolved

    def _load_prompt_config(self, name: str, context: dict) -> dict:
        """Load a YAML prompt configuration file.

        Resolution order:
        1. Project directory: {working_dir}/.aiwf/jpa-mt/templates/{name}
        2. Profile defaults: profiles/jpa_mt/templates/{name}

        Args:
            name: Config filename (e.g., "planning-prompt.yml")
            context: Workflow context (may contain "working_dir")

        Returns:
            Parsed YAML as dict

        Raises:
            FileNotFoundError: If config not found in any location
        """
        working_dir = Path(context.get("working_dir", ".")).resolve()

        # Check project override first (in templates/ subdirectory)
        project_path = working_dir / ".aiwf" / "jpa-mt" / "templates" / name
        if project_path.exists():
            logger.debug("Using project config: %s", project_path)
            with open(project_path, encoding="utf-8") as f:
                return yaml.safe_load(f)

        # Fall back to profile defaults (in templates/ subdirectory)
        profile_path = Path(__file__).parent / "templates" / name
        if profile_path.exists():
            logger.debug("Using profile config: %s", profile_path)
            with open(profile_path, encoding="utf-8") as f:
                return yaml.safe_load(f)

        raise FileNotFoundError(
            f"Prompt config not found: {name}\n"
            f"Searched:\n"
            f"  - {project_path}\n"
            f"  - {profile_path}"
        )

    # =========================================================================
    # PLANNING PROMPT SECTION BUILDERS
    # =========================================================================

    def _build_role_section(self, config: dict) -> list[str]:
        """Build the Role section of the planning prompt.

        This section defines the AI's persona and could become
        a system prompt in the future.

        Args:
            config: Loaded YAML config

        Returns:
            List of lines for the role section
        """
        return [
            f"# {config['role']['title']}",
            "",
            "## Role",
            "",
            config["role"]["description"].strip(),
            "",
            "---",
            "",
        ]

    def _build_planning_context_section(self, config: dict) -> list[str]:
        """Build the Context section with schema reference for planning prompt.

        Args:
            config: Loaded YAML config

        Returns:
            List of lines for the context section
        """
        lines = [
            "## Context",
            "",
            config["context"]["header"].strip(),
            "",
            config["context"]["schema_reference"].strip(),
            "",
        ]

        # Input Validation subsection (optional)
        if "input_validation" in config:
            iv = config["input_validation"]
            lines.extend([
                iv["header"],
                "",
                iv["content"].strip(),
                "",
            ])

        return lines

    def _build_conventions_section(self, config: dict) -> list[str]:
        """Build the Project Conventions section with naming/packages/technical tables.

        Args:
            config: Loaded YAML config

        Returns:
            List of lines for the conventions section
        """
        conv = config["conventions"]
        lines = ["### Project Conventions", ""]

        # Naming table
        lines.append(conv["naming"]["header"])
        lines.append("| Artifact | Pattern |")
        lines.append("|----------|---------|")
        for row in conv["naming"]["table"]:
            lines.append(f"| {row['artifact']} | `{row['pattern']}` |")
        lines.append("")

        # Packages table
        lines.append(conv["packages"]["header"])
        lines.append("| Artifact | Package |")
        lines.append("|----------|---------|")
        for row in conv["packages"]["table"]:
            lines.append(f"| {row['artifact']} | `{row['package']}` |")
        lines.append("")

        # Technical table
        lines.append(conv["technical"]["header"])
        lines.append("| Setting | Value |")
        lines.append("|---------|-------|")
        for row in conv["technical"]["table"]:
            lines.append(f"| {row['setting']} | `{row['value']}` |")
        lines.extend(["", "---", ""])

        return lines

    def _build_task_section(
        self, config: dict, artifacts: list[str], variables: dict[str, str]
    ) -> list[str]:
        """Build the Task section with common and artifact-specific phases.

        Args:
            config: Loaded YAML config
            artifacts: List of artifact types to generate
            variables: Resolved convention variables

        Returns:
            List of lines for the task section
        """
        lines = [
            "## Task",
            "",
            config["task"]["intro"].strip(),
            "",
        ]

        # Common phases
        for phase in config["task"]["common"]:
            lines.append(f"### {phase['phase']}")
            lines.append("")
            if "description" in phase:
                lines.append(phase["description"].strip())
                lines.append("")
            if "steps" in phase:
                for step in phase["steps"]:
                    lines.append(f"- {step}")
                lines.append("")

        # Artifact-specific phases
        artifact_phases = config["task"]["artifacts"]
        for artifact in artifacts:
            if artifact in artifact_phases:
                phase = artifact_phases[artifact]
                lines.append(f"### {phase['phase']}")
                lines.append("")
                # Handle conditional base entity step
                if artifact == "entity" and "base_entity_step_with_class" in phase:
                    base_entity_class = variables.get("base_entity_class", "")
                    if base_entity_class:
                        lines.append(f"- {phase['base_entity_step_with_class']}")
                    else:
                        lines.append(f"- {phase['base_entity_step_without_class']}")
                for step in phase["steps"]:
                    lines.append(f"- {step}")
                lines.append("")

        lines.extend(["---", ""])
        return lines

    def _build_standards_section(self) -> list[str]:
        """Build the Standards section with reference to standards bundle.

        Note: {{STANDARDS}} is an engine variable resolved by PromptAssembler.

        Returns:
            List of lines for the standards section
        """
        return [
            "## Standards",
            "",
            "Read the standards bundle at `{{STANDARDS}}`. This file contains the coding standards for this project, organized by category.",
            "",
            "Key areas to focus on:",
            "- JPA entity and repository standards (JPA-*)",
            "- Multi-tenancy patterns (MT-*)",
            "- Naming conventions (NAM-*, JV-NAM-*)",
            "- Package structure (PKG-*, DOM-*)",
            "",
            "You MUST cite rule IDs when making standards-based decisions.",
            "",
            "---",
            "",
        ]

    def _build_constraints_section(self, config: dict) -> list[str]:
        """Build the Constraints section with critical and technical requirements.

        Args:
            config: Loaded YAML config

        Returns:
            List of lines for the constraints section
        """
        constraints = config["constraints"]
        lines = [
            "## Constraints",
            "",
            constraints["critical"]["header"],
            "",
        ]
        for item in constraints["critical"]["items"]:
            lines.append(f"- {item}")
        lines.extend([
            "",
            constraints["technical"]["header"],
            "",
            constraints["technical"]["content"],
            "",
            "---",
            "",
        ])
        return lines

    def _build_expected_output_section(
        self, config: dict, artifacts: list[str], variables: dict[str, str]
    ) -> list[str]:
        """Build the Expected Output section with format template.

        Args:
            config: Loaded YAML config
            artifacts: List of artifact types
            variables: Resolved convention variables

        Returns:
            List of lines for the expected output section
        """
        expected = config["expected_output"]
        lines = [
            "## Expected Output",
            "",
            expected["intro"],
            "",
            "```markdown",
            "# Implementation Plan: {{entity}}",
            "",
        ]

        # Common sections
        for section in expected["common"]:
            lines.append(f"## {section['section']}")
            for item in section["items"]:
                lines.append(f"- {item}")
            lines.append("")

        # Artifact-specific sections
        artifact_sections = expected["artifacts"]
        for artifact in artifacts:
            if artifact in artifact_sections:
                section = artifact_sections[artifact]
                lines.append(f"## {section['section']}")
                # Handle conditional extends item
                if artifact == "entity" and "extends_item_with_class" in section:
                    base_entity_class = variables.get("base_entity_class", "")
                    if base_entity_class:
                        lines.append(f"- {section['extends_item_with_class']}")
                    else:
                        lines.append(f"- {section['extends_item_without_class']}")
                for item in section["items"]:
                    lines.append(f"- {item}")
                lines.append("")

        # Closing sections (e.g., Open Questions)
        for section in expected["closing"]:
            lines.append(f"## {section['section']}")
            # Select guidance based on assume_answers config
            guidance_key = "guidance_assume" if self.config.assume_answers else "guidance_manual"
            if guidance_key in section:
                lines.extend(["", section[guidance_key].strip(), ""])
            elif "guidance" in section:
                lines.extend(["", section["guidance"].strip(), ""])
            for item in section["items"]:
                lines.append(f"- {item}")
            lines.append("")

        lines.extend(["```", "", "---", ""])
        return lines

    def _build_checklist_section(
        self, config: dict, variables: dict[str, str]
    ) -> list[str]:
        """Build the Pre-Output Checklist section.

        Args:
            config: Loaded YAML config
            variables: Resolved convention variables

        Returns:
            List of lines for the checklist section (empty if not configured)
        """
        if "pre_output_checklist" not in config:
            return []

        poc = config["pre_output_checklist"]
        lines = [
            poc["header"],
            "",
            poc["intro"],
            "",
        ]

        # First two items
        for item in poc["items"][:2]:
            lines.append(f"- {item}")

        # Conditional base entity check (after multi-tenancy)
        if "base_entity_check_with_class" in poc:
            base_entity_class = variables.get("base_entity_class", "")
            if base_entity_class:
                lines.append(f"- {poc['base_entity_check_with_class']}")
            else:
                lines.append(f"- {poc['base_entity_check_without_class']}")

        # Remaining items
        for item in poc["items"][2:]:
            lines.append(f"- {item}")

        lines.extend(["", "---", ""])
        return lines

    def _build_instructions_section(self, config: dict) -> list[str]:
        """Build the Instructions section.

        Args:
            config: Loaded YAML config

        Returns:
            List of lines for the instructions section
        """
        lines = ["## Instructions", ""]
        for i, item in enumerate(config["instructions"]["items"], 1):
            lines.append(f"{i}. {item}")
        lines.append("")
        return lines

    def _build_planning_prompt_from_yaml(
        self, context: dict, artifacts: list[str], variables: dict[str, str]
    ) -> str:
        """Build planning prompt from YAML configuration.

        Loads planning-prompt.yml and assembles the prompt by delegating
        to section-specific builder methods.

        Args:
            context: Workflow context dict
            artifacts: List of artifact types to generate
            variables: Resolved convention variables (for conditional logic)

        Returns:
            Assembled markdown prompt (with {{var}} placeholders intact)
        """
        config = self._load_prompt_config("planning-prompt.yml", context)
        lines: list[str] = []

        # Assemble sections in order
        lines.extend(self._build_role_section(config))
        lines.extend(self._build_planning_context_section(config))
        lines.extend(self._build_conventions_section(config))
        lines.extend(self._build_task_section(config, artifacts, variables))
        lines.extend(self._build_standards_section())
        lines.extend(self._build_constraints_section(config))
        lines.extend(self._build_expected_output_section(config, artifacts, variables))
        lines.extend(self._build_checklist_section(config, variables))
        lines.extend(self._build_instructions_section(config))

        return "\n".join(lines)

    # =========================================================================
    # PROMPT GENERATION
    # =========================================================================

    def generate_planning_prompt(self, context: dict) -> PromptResult:
        """Generate planning phase prompt.

        Builds the prompt from planning-prompt.yml configuration,
        assembling sections based on the requested scope/artifacts.
        Uses multi-pass variable resolution when conventions are specified.
        """
        scope = context.get("scope", "domain")
        scope_config = self.config.scopes.get(scope)

        if not scope_config:
            raise ValueError(f"Unknown scope: {scope}")

        # Get convention name from context (optional)
        convention_name = context.get("conventions")

        # Build complete variable dict from context and conventions FIRST
        # (needed for conditional logic in prompt builder)
        variables = self._build_variables(context, convention_name)

        # Add computed variables
        variables["artifacts"] = ", ".join(scope_config.artifacts)

        # Build prompt from YAML configuration (with {{var}} placeholders)
        # Pass variables for conditional logic (e.g., base_entity_class)
        prompt = self._build_planning_prompt_from_yaml(
            context, scope_config.artifacts, variables
        )

        # Note: Standards are referenced by file path, not embedded (see _build_planning_prompt_from_yaml)

        # Apply multi-pass variable resolution
        return self._resolve_variables(prompt, variables)

    def _get_standards_for_context(self, context: dict) -> str:
        """Get standards bundle for the current context.

        Uses the standards provider to generate a filtered standards bundle
        based on the current scope.

        Args:
            context: Workflow context with scope

        Returns:
            Markdown-formatted standards bundle
        """
        try:
            config = self.get_standards_config()
            provider = JpaMtStandardsProvider(config)
            provider.validate()
            return provider.create_bundle(context)
        except Exception as e:
            # Fall back to summary if provider fails
            logger.warning("Standards provider failed: %s", e)
            return self._get_standards_summary(context)

    def generate_generation_prompt(self, context: dict) -> PromptResult:
        """Generate code generation phase prompt.

        Loads the generation-prompt.md template and substitutes placeholders
        with values from context and profile configuration.
        """
        scope = context.get("scope", "domain")
        scope_config = self.config.scopes.get(scope)

        if not scope_config:
            raise ValueError(f"Unknown scope: {scope}")

        # Build extra variables for template substitution
        extra_vars = {
            "artifacts": ", ".join(scope_config.artifacts),
            "standards": self._get_standards_for_context(context),
            "iteration": str(context.get("iteration", 1)),
        }

        return self._load_template("generation-prompt.md", context, extra_vars)

    def generate_review_prompt(self, context: dict) -> PromptResult:
        """Generate code review phase prompt.

        Loads the review-prompt.md template and substitutes placeholders
        with values from context and profile configuration.
        """
        scope = context.get("scope", "domain")
        scope_config = self.config.scopes.get(scope)

        if not scope_config:
            raise ValueError(f"Unknown scope: {scope}")

        # Build extra variables for template substitution
        extra_vars = {
            "artifacts": ", ".join(scope_config.artifacts),
            "standards": self._get_standards_for_context(context),
        }

        return self._load_template("review-prompt.md", context, extra_vars)

    def generate_revision_prompt(self, context: dict) -> PromptResult:
        """Generate revision phase prompt.

        Loads the revision-prompt.md template and substitutes placeholders
        with values from context and profile configuration.
        """
        scope = context.get("scope", "domain")
        scope_config = self.config.scopes.get(scope)

        if not scope_config:
            raise ValueError(f"Unknown scope: {scope}")

        # Build extra variables for template substitution
        extra_vars = {
            "artifacts": ", ".join(scope_config.artifacts),
            "standards": self._get_standards_for_context(context),
            "iteration": str(context.get("iteration", 1)),
        }

        return self._load_template("revision-prompt.md", context, extra_vars)

    # =========================================================================
    # RESPONSE PROCESSING
    # =========================================================================

    def process_planning_response(self, content: str) -> ProcessingResult:
        """Process planning response."""
        # For now, accept any non-empty response
        if not content or not content.strip():
            return ProcessingResult(
                status=WorkflowStatus.ERROR,
                error_message="Empty planning response",
            )

        return ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            messages=["Planning response received"],
        )

    def process_generation_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        """Process generation response and extract code blocks.

        Extracts Java code blocks from markdown format:
        ```java
        // Filename.java
        package ...;
        ...
        ```
        """
        if not content or not content.strip():
            return ProcessingResult(
                status=WorkflowStatus.ERROR,
                error_message="Empty generation response",
            )

        # Extract code blocks using regex
        # Pattern: ```java\n// Filename.java\n...content...```
        code_block_pattern = re.compile(
            r'```java\s*\n'           # Opening fence
            r'//\s*(\S+\.java)\s*\n'  # Filename comment
            r'(.*?)'                   # Content (non-greedy)
            r'\n```',                  # Closing fence
            re.DOTALL
        )

        writes: list[WriteOp] = []
        for match in code_block_pattern.finditer(content):
            filename = match.group(1)
            code_content = match.group(2).strip()

            if code_content:
                writes.append(WriteOp(path=filename, content=code_content))
                logger.debug(f"Extracted code file: {filename} ({len(code_content)} chars)")

        if writes:
            return ProcessingResult(
                status=WorkflowStatus.IN_PROGRESS,
                messages=[f"Extracted {len(writes)} code file(s)"],
                write_plan=WritePlan(writes=writes),
            )
        else:
            # No code blocks found - might be an error or empty response
            logger.warning("No Java code blocks found in generation response")
            return ProcessingResult(
                status=WorkflowStatus.IN_PROGRESS,
                messages=["Generation response received (no code blocks found)"],
            )

    def process_review_response(self, content: str) -> ProcessingResult:
        """Process review response and extract verdict per ADR-0004."""
        if not content or not content.strip():
            return ProcessingResult(
                status=WorkflowStatus.ERROR,
                error_message="Empty review response",
            )

        try:
            metadata = parse_review_metadata(content)
        except ParseError as e:
            return ProcessingResult(
                status=WorkflowStatus.ERROR,
                error_message=f"Failed to parse @@@REVIEW_META: {e}",
            )

        summary = format_review_summary(metadata)

        if metadata.verdict == ReviewVerdict.PASS:
            return ProcessingResult(
                status=WorkflowStatus.SUCCESS,
                approved=True,
                messages=[f"REVIEW: {summary}"],
                metadata={
                    "verdict": metadata.verdict.value,
                    "issues_total": metadata.issues_total,
                    "issues_critical": metadata.issues_critical,
                    "missing_inputs": metadata.missing_inputs,
                },
            )
        else:
            # FAIL -> needs revision
            return ProcessingResult(
                status=WorkflowStatus.FAILED,
                approved=False,
                messages=[f"REVIEW: {summary}"],
                metadata={
                    "verdict": metadata.verdict.value,
                    "issues_total": metadata.issues_total,
                    "issues_critical": metadata.issues_critical,
                    "missing_inputs": metadata.missing_inputs,
                },
            )

    def process_revision_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        """Process revision response."""
        # Same as generation
        return self.process_generation_response(content, session_dir, iteration)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _build_context_section(self, context: dict) -> str:
        """Build the context section for prompts."""
        parts = [
            f"Entity: {context.get('entity', 'Unknown')}",
            f"Table: {context.get('table', 'Unknown')}",
            f"Bounded Context: {context.get('bounded_context', 'Unknown')}",
            f"Scope: {context.get('scope', 'domain')}",
        ]

        if context.get("schema_ddl"):
            parts.append(f"\n## Schema DDL\n```sql\n{context['schema_ddl']}\n```")

        if context.get("plan"):
            parts.append(f"\n## Approved Plan\n{context['plan']}")

        return "\n".join(parts)

    def _get_standards_summary(self, context: dict) -> str:
        """Get standards rules for inclusion in prompts."""
        # TODO: Load from YAML files based on scope
        # For now, return placeholder
        return """## Standards
Follow all JPA-*, PKG-*, NAM-*, JV-* rules from the standards bundle.
Key rules:
- JPA-ENT-001: Explicit @Table(schema, name)
- JPA-TYPE-002: Use OffsetDateTime for timestamps
- JV-DI-001: Constructor injection only
"""

    def _get_expected_files(self, context: dict, artifacts: list[str]) -> list[str]:
        """Get list of expected output files for the given artifacts."""
        entity = context.get("entity", "Entity")
        files = []

        for artifact in artifacts:
            if artifact == "entity":
                files.append(f"{entity}.java")
            elif artifact == "repository":
                files.append(f"{entity}Repository.java")
            elif artifact == "service":
                files.append(f"{entity}Service.java")
            elif artifact == "controller":
                files.append(f"{entity}Controller.java")
            elif artifact == "dto":
                files.append(f"{entity}Request.java")
                files.append(f"{entity}Response.java")
            elif artifact == "mapper":
                files.append(f"{entity}Mapper.java")

        return files

    def _build_expected_output(self, context: dict, artifacts: list[str]) -> str:
        """Build the expected output section for planning prompt.

        Generates artifact-specific design sections based on the scope.

        Args:
            context: Workflow context dict
            artifacts: List of artifact types to generate

        Returns:
            Markdown-formatted expected output section
        """
        entity = context.get("entity", "{{entity}}")

        # Start with intro and common sections
        lines = [
            f"Create a file named `plan.md` with the following structure:",
            "",
            "```markdown",
            f"# Implementation Plan: {entity}",
            "",
            "## Schema Analysis",
            f"- Table: {context.get('table', '{{table}}')}",
            "- Columns: [table of columns with types]",
            "- Relationships: [identified FKs and their targets]",
            "",
            "## Multi-Tenancy",
            "- Classification: [Global/Tenant-Scoped/Top-Level]",
            "- Scoping Strategy: [how tenant isolation is enforced]",
        ]

        # Add artifact-specific design sections
        design_sections = {
            "entity": [
                "",
                "## Entity Design",
                "- Extends: BaseEntity | None",
                "- Fields: [table mapping column -> field -> type]",
                "- Relationships: [ManyToOne/OneToMany with fetch/cascade]",
                "- Validations: [@NotNull, @Size, etc.]",
            ],
            "repository": [
                "",
                "## Repository Design",
                "- Standard Methods: [list with signatures]",
                "- Custom Queries: [any @Query methods needed]",
            ],
            "service": [
                "",
                "## Service Design",
                "- Public Methods: [list with signatures]",
                "- Transaction Boundaries: [where @Transactional applies]",
                "- Dependencies: [repositories or other services needed]",
            ],
            "controller": [
                "",
                "## Controller Design",
                "- Endpoints: [HTTP method, path, description]",
                "- Request/Response: [DTO types for each endpoint]",
                "- Security: [authorization requirements]",
            ],
            "dto": [
                "",
                "## DTO Design",
                "- Request DTO: [fields for create/update operations]",
                "- Response DTO: [fields to expose in responses]",
                "- Validation: [field constraints]",
            ],
            "mapper": [
                "",
                "## Mapper Design",
                "- Entity → Response: [mapping strategy]",
                "- Request → Entity: [mapping strategy]",
                "- Special Handling: [nested objects, collections]",
            ],
        }

        for artifact in artifacts:
            if artifact in design_sections:
                lines.extend(design_sections[artifact])

        # Add File List section with artifact-specific entries
        lines.extend([
            "",
            "## File List",
            "",
            "Files to generate (use the package and naming conventions above):",
            "",
            "| File | Package | Class |",
            "|------|---------|-------|",
        ])

        # File list entries per artifact
        file_list_entries = {
            "entity": "| Entity | `{{entity_package}}` | `{{entity_class}}` |",
            "repository": "| Repository | `{{repository_package}}` | `{{repository_class}}` |",
            "service": "| Service | `{{service_package}}` | `{{service_class}}` |",
            "controller": "| Controller | `{{controller_package}}` | `{{controller_class}}` |",
            "dto": "| Request DTO | `{{dto_package}}` | `{{dto_request_class}}` |\n| Response DTO | `{{dto_package}}` | `{{dto_response_class}}` |",
            "mapper": "| Mapper | `{{mapper_package}}` | `{{mapper_class}}` |",
        }

        for artifact in artifacts:
            if artifact in file_list_entries:
                lines.append(file_list_entries[artifact])

        # Add common closing sections
        lines.extend([
            "",
            "## Open Questions",
            "- [Any uncertainties or decisions needing human input]",
            "",
            "## Standards Compliance",
            "- [List applicable rules and how they'll be satisfied]",
            "```",
        ])

        return "\n".join(lines)

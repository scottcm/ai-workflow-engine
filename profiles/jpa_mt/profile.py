"""JPA-MT Profile Implementation (v2).

Multi-tenant JPA code generation for Spring/Hibernate environments.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.profiles.workflow_profile import PromptResult, WorkflowProfile

from .config import JpaMtConfig
from .standards import JpaMtStandardsProvider

# Register the standards provider with the factory
from aiwf.domain.standards import StandardsProviderFactory
StandardsProviderFactory.register("yaml-rules", JpaMtStandardsProvider)

logger = logging.getLogger(__name__)


class JpaMtProfile(WorkflowProfile):
    """Multi-tenant JPA domain layer generation profile (v2)."""

    def __init__(self, config: JpaMtConfig | None = None):
        self.config = config or JpaMtConfig()

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
        # Get rules_path from config sources, or use default
        rules_path = None
        if self.config.standards.sources:
            # Use first source path
            rules_path = self.config.standards.sources[0].path

        # Default to LIVE/experimental for YAML rules
        if not rules_path:
            rules_path = str(Path(__file__).parent.parent.parent / "LIVE" / "experimental")

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

    def _resolve_variables(
        self,
        text: str,
        variables: dict[str, str],
        max_passes: int = 3,
    ) -> str:
        """Multi-pass variable substitution.

        Repeatedly substitutes {{var}} placeholders until no more remain
        or max_passes is reached. This allows variables to reference other
        variables (e.g., entity_package uses base_package).

        Args:
            text: Text with {{var}} placeholders
            variables: Dict of variable name -> value
            max_passes: Maximum substitution passes (default: 3)

        Returns:
            Text with variables substituted (unresolved placeholders left as-is)
        """
        pattern = re.compile(r"\{\{(\w+)\}\}")

        for pass_num in range(max_passes):
            def replace(match: re.Match) -> str:
                key = match.group(1)
                return variables.get(key, match.group(0))

            new_text = pattern.sub(replace, text)
            if new_text == text:
                # No changes made, stop early
                break
            text = new_text

        # Warn about unresolved variables
        unresolved = pattern.findall(text)
        if unresolved:
            unique = sorted(set(unresolved))
            logger.warning("Unresolved placeholders: %s", unique)

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

    def _build_planning_prompt_from_yaml(
        self, context: dict, artifacts: list[str]
    ) -> str:
        """Build planning prompt from YAML configuration.

        Loads planning-prompt.yml and assembles the prompt based on
        the requested artifacts.

        Args:
            context: Workflow context dict
            artifacts: List of artifact types to generate

        Returns:
            Assembled markdown prompt (with {{var}} placeholders intact)
        """
        config = self._load_prompt_config("planning-prompt.yml", context)
        lines: list[str] = []

        # --- Role Section ---
        lines.append(f"# {config['role']['title']}")
        lines.append("")
        lines.append("## Role")
        lines.append("")
        lines.append(config["role"]["description"].strip())
        lines.append("")
        lines.append("---")
        lines.append("")

        # --- Context Section ---
        lines.append("## Context")
        lines.append("")
        lines.append(config["context"]["header"].strip())
        lines.append("")
        lines.append(config["context"]["schema_reference"].strip())
        lines.append("")

        # --- Conventions Section ---
        lines.append("### Project Conventions")
        lines.append("")

        # Naming table
        conv = config["conventions"]
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
        lines.append("")
        lines.append("---")
        lines.append("")

        # --- Task Section ---
        lines.append("## Task")
        lines.append("")
        lines.append(config["task"]["intro"].strip())
        lines.append("")

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
                for step in phase["steps"]:
                    lines.append(f"- {step}")
                lines.append("")

        lines.append("---")
        lines.append("")

        # --- Standards Section ---
        # Note: {{STANDARDS}} is an engine variable resolved by PromptAssembler
        lines.append("## Standards")
        lines.append("")
        lines.append("Read the standards bundle at `{{STANDARDS}}`. This file contains the coding standards for this project, organized by category.")
        lines.append("")
        lines.append("Key areas to focus on:")
        lines.append("- JPA entity and repository standards (JPA-*)")
        lines.append("- Multi-tenancy patterns (MT-*)")
        lines.append("- Naming conventions (NAM-*, JV-NAM-*)")
        lines.append("- Package structure (PKG-*, DOM-*)")
        lines.append("")
        lines.append("You MUST cite rule IDs when making standards-based decisions.")
        lines.append("")
        lines.append("---")
        lines.append("")

        # --- Constraints Section ---
        constraints = config["constraints"]
        lines.append("## Constraints")
        lines.append("")
        lines.append(constraints["critical"]["header"])
        lines.append("")
        for item in constraints["critical"]["items"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append(constraints["technical"]["header"])
        lines.append("")
        lines.append(constraints["technical"]["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

        # --- Expected Output Section ---
        expected = config["expected_output"]
        lines.append("## Expected Output")
        lines.append("")
        lines.append(expected["intro"])
        lines.append("")
        lines.append("```markdown")
        lines.append(f"# Implementation Plan: {{{{entity}}}}")
        lines.append("")

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
                for item in section["items"]:
                    lines.append(f"- {item}")
                lines.append("")

        # File list
        lines.append("## File List")
        lines.append("")
        lines.append(expected["file_list"]["header"])
        lines.append("")
        lines.append("| File | Package | Class |")
        lines.append("|------|---------|-------|")

        file_entries = expected["file_list"]["entries"]
        for key, entry in file_entries.items():
            # Check if this entry belongs to the requested artifacts
            entry_artifact = entry.get("artifact", key)
            if entry_artifact in artifacts:
                lines.append(
                    f"| {entry['file']} | `{entry['package']}` | `{entry['class']}` |"
                )
        lines.append("")

        # Closing sections
        for section in expected["closing"]:
            lines.append(f"## {section['section']}")
            for item in section["items"]:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

        # --- Instructions Section ---
        lines.append("## Instructions")
        lines.append("")
        for i, item in enumerate(config["instructions"]["items"], 1):
            lines.append(f"{i}. {item}")
        lines.append("")

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

        # Build prompt from YAML configuration (with {{var}} placeholders)
        prompt = self._build_planning_prompt_from_yaml(context, scope_config.artifacts)

        # Get convention name from context (optional)
        convention_name = context.get("conventions")

        # Build complete variable dict from context and conventions
        variables = self._build_variables(context, convention_name)

        # Add computed variables
        variables["artifacts"] = ", ".join(scope_config.artifacts)
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
        """Process generation response."""
        # For now, accept any non-empty response
        # TODO: Parse code blocks, validate expected files exist
        if not content or not content.strip():
            return ProcessingResult(
                status=WorkflowStatus.ERROR,
                error_message="Empty generation response",
            )

        return ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            messages=["Generation response received"],
        )

    def process_review_response(self, content: str) -> ProcessingResult:
        """Process review response and extract verdict."""
        # TODO: Parse @@@REVIEW_META to extract PASS/FAIL verdict
        if not content or not content.strip():
            return ProcessingResult(
                status=WorkflowStatus.ERROR,
                error_message="Empty review response",
            )

        # For now, assume review passes
        # TODO: Parse @@@REVIEW_META to extract PASS/FAIL verdict
        return ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            approved=True,
            messages=["Review complete (TODO: parse verdict)"],
            metadata={"verdict": "PASS"},
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

"""JPA-MT Profile Implementation (v2).

Multi-tenant JPA code generation for Spring/Hibernate environments.
"""

import logging
import re
from pathlib import Path
from typing import Any

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

    # =========================================================================
    # PROMPT GENERATION
    # =========================================================================

    def generate_planning_prompt(self, context: dict) -> PromptResult:
        """Generate planning phase prompt.

        Loads the planning-prompt.md template and substitutes placeholders
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

        return self._load_template("planning-prompt.md", context, extra_vars)

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
        """Generate code generation phase prompt."""
        scope = context.get("scope", "domain")
        scope_config = self.config.scopes.get(scope)

        if not scope_config:
            raise ValueError(f"Unknown scope: {scope}")

        expected_files = self._get_expected_files(context, scope_config.artifacts)

        parts = [
            "# Role",
            "You are a senior Java developer implementing JPA entities and repositories.",
            "",
            "# Context",
            self._build_context_section(context),
            "",
            "# Task",
            f"Implement the {context['entity']} entity based on the approved plan.",
            "",
            "Generate these files:",
            *[f"- {f}" for f in expected_files],
            "",
            "Follow the standards strictly. Write complete, production-ready code.",
            "",
            "# Standards",
            self._get_standards_summary(context),
            "",
            "# Expected Output",
            "Create the following files:",
            *[f"- {f}" for f in expected_files],
        ]
        return "\n".join(parts)

    def generate_review_prompt(self, context: dict) -> PromptResult:
        """Generate code review phase prompt."""
        parts = [
            "# Role",
            "You are a senior code reviewer checking for standards compliance.",
            "",
            "# Context",
            self._build_context_section(context),
            "",
            "# Task",
            "Review the generated code for:",
            "1. Standards compliance (check each rule)",
            "2. Multi-tenancy correctness",
            "3. JPA best practices",
            "4. Potential bugs or issues",
            "",
            "Cite specific rule IDs for any violations found.",
            "",
            "# Standards",
            self._get_standards_summary(context),
            "",
            "# Expected Output",
            "Create a file named `review.md` with:",
            "- Summary (PASS/FAIL)",
            "- Findings table (Rule ID, Severity, Description, Location)",
            "- @@@REVIEW_META section with structured verdict",
        ]
        return "\n".join(parts)

    def generate_revision_prompt(self, context: dict) -> PromptResult:
        """Generate revision phase prompt."""
        scope = context.get("scope", "domain")
        scope_config = self.config.scopes.get(scope)

        if not scope_config:
            raise ValueError(f"Unknown scope: {scope}")

        expected_files = self._get_expected_files(context, scope_config.artifacts)

        parts = [
            "# Role",
            "You are a senior Java developer fixing review findings.",
            "",
            "# Context",
            self._build_context_section(context),
            "",
            "# Task",
            "Fix all review findings from the previous iteration.",
            "",
            "Address each finding by rule ID. Regenerate the complete files.",
            "",
            "# Standards",
            self._get_standards_summary(context),
            "",
            "# Expected Output",
            "Create the following files with fixes applied:",
            *[f"- {f}" for f in expected_files],
        ]
        return "\n".join(parts)

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

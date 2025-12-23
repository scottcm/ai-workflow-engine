from pathlib import Path
from typing import Any
import re

import yaml

from aiwf.domain.profiles.workflow_profile import WorkflowProfile
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.application.standards_provider import StandardsProvider
from profiles.jpa_mt.jpa_mt_standards_provider import JpaMtStandardsProvider
from profiles.jpa_mt.jpa_mt_config import JpaMtConfig

# Path to default config.yml relative to this file
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yml"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


class JpaMtProfile(WorkflowProfile):
    def __init__(self, **config):
        # Load default config from config.yml if no config provided
        if not config and _DEFAULT_CONFIG_PATH.exists():
            with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        model = JpaMtConfig.model_validate(config)
        self.config = model.model_dump()

    def validate_metadata(self, metadata: dict[str, Any] | None) -> None:
        """Validate that required metadata is provided for jpa-mt profile."""
        if not metadata or "schema_file" not in metadata:
            raise ValueError("jpa-mt profile requires --schema-file argument")

    def get_standards_provider(self) -> StandardsProvider:
        """Return JPA-MT specific standards provider."""
        return JpaMtStandardsProvider(self.config)

    def _load_template(self, phase: str, scope: str) -> tuple[str, Path]:
        """Load a template file for the given phase and scope.

        Returns tuple of (content, template_path) for include resolution.
        """
        template_path = _TEMPLATES_DIR / phase / f"{scope}.md"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        return template_path.read_text(encoding="utf-8"), template_path

    def _resolve_includes(
        self, content: str, base_path: Path, seen: set[str] | None = None
    ) -> str:
        """Resolve {{include: path}} directives recursively.

        Args:
            content: The template content with include directives
            base_path: The path of the file containing this content (for relative resolution)
            seen: Set of already-included paths to detect circular includes
        """
        if seen is None:
            seen = set()

        include_pattern = re.compile(r"\{\{include:\s*([^}]+)\}\}")

        def replace_include(match: re.Match) -> str:
            include_path = match.group(1).strip()

            # Resolve relative to the current file's directory
            full_path = (base_path.parent / include_path).resolve()

            if str(full_path) in seen:
                raise RuntimeError(f"Circular include detected: {include_path}")

            if not full_path.exists():
                raise FileNotFoundError(f"Include not found: {full_path}")

            seen.add(str(full_path))
            included_content = full_path.read_text(encoding="utf-8")
            return self._resolve_includes(included_content, full_path, seen)

        return include_pattern.sub(replace_include, content)

    def _fill_placeholders(self, content: str, context: dict[str, Any]) -> str:
        """Replace {{PLACEHOLDER}} with context values.

        Special handling:
        - schema_file: if provided, reads file content as {{SCHEMA_DDL}}
        - code_files: if provided, formats as markdown list for {{CODE_FILES}}
        """
        # Read schema file content if path provided
        effective_context = dict(context)
        schema_file = effective_context.get("schema_file")
        if schema_file:
            schema_path = Path(schema_file)
            if not schema_path.is_absolute():
                schema_path = Path.cwd() / schema_file
            if not schema_path.exists():
                raise FileNotFoundError(f"Schema file not found: {schema_path}")
            effective_context["schema_ddl"] = schema_path.read_text(encoding="utf-8")
        else:
            effective_context["schema_ddl"] = ""

        # Format code_files list as markdown
        code_files = effective_context.get("code_files")
        if code_files and isinstance(code_files, list):
            effective_context["code_files"] = "\n".join(f"- `{f}`" for f in code_files)
        elif code_files is None:
            effective_context["code_files"] = ""

        result = content
        for key, value in effective_context.items():
            placeholder = f"{{{{{key.upper()}}}}}"
            display_value = "" if value is None else str(value)
            result = result.replace(placeholder, display_value)
        return result

    def generate_planning_prompt(self, context: dict) -> str:
        """Generate planning prompt from template."""
        scope = context.get("scope", "domain")
        template, template_path = self._load_template("planning", scope)
        resolved = self._resolve_includes(template, template_path)
        return self._fill_placeholders(resolved, context)

    def generate_generation_prompt(self, context: dict) -> str:
        """Generate generation prompt from template."""
        scope = context.get("scope", "domain")
        template, template_path = self._load_template("generation", scope)
        resolved = self._resolve_includes(template, template_path)
        return self._fill_placeholders(resolved, context)

    def generate_review_prompt(self, context: dict) -> str:
        """Generate review prompt from template."""
        scope = context.get("scope", "domain")
        template, template_path = self._load_template("review", scope)
        resolved = self._resolve_includes(template, template_path)
        return self._fill_placeholders(resolved, context)

    def generate_revision_prompt(self, context: dict) -> str:
        """Generate revision prompt from template."""
        scope = context.get("scope", "domain")
        template, template_path = self._load_template("revision", scope)
        resolved = self._resolve_includes(template, template_path)
        return self._fill_placeholders(resolved, context)

    def process_planning_response(self, content: str) -> ProcessingResult:
        """Process planning response - validate it's non-empty."""
        if not content or not content.strip():
            return ProcessingResult(status=WorkflowStatus.ERROR)
        return ProcessingResult(status=WorkflowStatus.SUCCESS)
    
    def process_generation_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        """Process generation response - extract code files from response."""
        from aiwf.domain.models.write_plan import WriteOp, WritePlan

        if not content or not content.strip():
            return ProcessingResult(status=WorkflowStatus.ERROR)

        # Extract code blocks from markdown
        code_blocks = self._extract_code_blocks(content)
        if not code_blocks:
            return ProcessingResult(status=WorkflowStatus.ERROR)

        # Build write plan from extracted files
        writes = []
        for filename, code in code_blocks.items():
            writes.append(WriteOp(
                path=f"iteration-{iteration}/code/{filename}",
                content=code,
            ))

        return ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=writes),
        )

    def _extract_code_blocks(self, content: str) -> dict[str, str]:
        """Extract code files from markdown code blocks with // FILE: comments."""
        files = {}
        # Match markdown code blocks with java language
        code_block_pattern = re.compile(
            r"```(?:java)?\s*\n(.*?)```",
            re.DOTALL
        )

        for match in code_block_pattern.finditer(content):
            block_content = match.group(1)
            # Look for // FILE: filename at the start
            file_match = re.match(r"//\s*FILE:\s*(\S+\.java)\s*\n", block_content)
            if file_match:
                filename = file_match.group(1)
                # Extract code after the FILE comment
                code = block_content[file_match.end():]
                files[filename] = code.strip()

        return files
    
    def process_review_response(self, content: str) -> ProcessingResult:
        """Process review response - parse metadata and determine pass/fail.

        Returns:
            ProcessingResult with:
            - SUCCESS if verdict is PASS
            - FAILED if verdict is FAIL
            - ERROR if content is empty or metadata is missing/malformed
        """
        from profiles.jpa_mt.review_metadata import parse_review_metadata

        if not content or not content.strip():
            return ProcessingResult(status=WorkflowStatus.ERROR)

        metadata = parse_review_metadata(content)
        if metadata is None:
            return ProcessingResult(status=WorkflowStatus.ERROR)

        if metadata["verdict"] == "PASS":
            return ProcessingResult(status=WorkflowStatus.SUCCESS)
        else:  # verdict == "FAIL"
            return ProcessingResult(status=WorkflowStatus.FAILED)
    
    def process_revision_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        """Process revision response - extract corrected code files.

        Same as generation response processing - extracts code blocks with WritePlan.
        """
        from aiwf.domain.models.write_plan import WriteOp, WritePlan

        if not content or not content.strip():
            return ProcessingResult(status=WorkflowStatus.ERROR)

        # Extract code blocks from markdown (same as generation)
        code_blocks = self._extract_code_blocks(content)
        if not code_blocks:
            return ProcessingResult(status=WorkflowStatus.ERROR)

        # Build write plan from extracted files
        writes = []
        for filename, code in code_blocks.items():
            writes.append(WriteOp(
                path=f"iteration-{iteration}/code/{filename}",
                content=code,
            ))

        return ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=writes),
        )
    
    
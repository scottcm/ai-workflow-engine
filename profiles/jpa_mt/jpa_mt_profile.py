from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import yaml
import logging
import re

from aiwf.domain.profiles import WorkflowProfile
from aiwf.domain.models.workflow_state import WorkflowPhase
from aiwf.domain.validation import (
    PathValidator,
    validate_standards_root,
    validate_standards_file,
    validate_target_root,
)


class JpaMtProfile(WorkflowProfile):
    """
    Multi-tenant JPA code generation profile.
    
    Supports multiple scopes:
    - domain: Entity + Repository
    - vertical: Full stack (Entity → Controller)
    
    Uses configuration-driven standards bundling with layer-based mapping.
    """
   
    def __init__(self, config_path: Path | None = None, **config: Any):
        """
        Initialize the profile.
        
        Args:
            config_path: Path to config.yml (default: profile_root/config.yml)
            **config: Optional config dict (for testing, overrides file)
        """
        self.profile_root = Path(__file__).parent
        
        # Load configuration
        if config:
            # Config passed directly (testing)
            self.config = config
        else:
            # Load from YAML file
            config_file = config_path or (self.profile_root / "config.yml")
            self.config = self._load_and_validate_config(config_file)
        
        # Set up directories from config
        self.templates_dir = self.profile_root / "templates"
        self.standards_root = self._resolve_standards_root()
        
        # Validate scopes exist in config
        if "scopes" not in self.config:
            raise ValueError("Config missing 'scopes' section")
        if "layer_standards" not in self.config:
            raise ValueError("Config missing 'layer_standards' section")

    def _load_and_validate_config(self, config_path: Path) -> dict[str, Any]:
        """
        Load config.yml and perform basic validation.

        TODO: Replace with Pydantic model validation.
        """
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # TODO: Add Pydantic validation model
        # For now, basic validation
        required = ["standards", "artifacts", "scopes", "layer_standards"]
        missing = [key for key in required if key not in config]
        if missing:
            raise ValueError(f"Config missing required sections: {missing}")
        
        return config

    def _resolve_standards_root(self) -> Path:
        """Resolve standards root from config, handling env vars and relative paths."""
        
        standards_config = self.config.get("standards", {})
        raw = Path(self.config["standards"]["root"])

        if not raw.is_absolute():
            raw = self.profile_root / raw

        return validate_standards_root(raw)


    def prompt_template_for(self, phase: WorkflowPhase, scope: str = "domain") -> Path:
        """
        Get the path to the prompt template for the given phase and scope.
        
        Templates are organized as: templates/{phase_dir}/{scope}.md
        
        Args:
            phase: The workflow phase
            scope: The generation scope (e.g., "domain", "vertical")
            
        Returns:
            Path to the prompt template file
            
        Raises:
            ValueError: If no template defined for phase or invalid scope
            FileNotFoundError: If template file doesn't exist
        """
        # Validate scope exists in config
        if scope not in self.config["scopes"]:
            available = list(self.config["scopes"].keys())
            raise ValueError(
                f"Invalid scope '{scope}'. Available: {available}"
            )

        # Map phases to template files
        phase_dir_map  = {
            WorkflowPhase.INITIALIZED: "planning",
            WorkflowPhase.PLANNED: "generation",
            WorkflowPhase.GENERATED: "review",
            WorkflowPhase.REVIEWED: "revision",
        }

        phase_dir = phase_dir_map.get(phase)
        if not phase_dir:
            raise ValueError(f"No template defined for phase: {phase}")
        
        # Build path: templates/{phase_dir}/{scope}.md
        template_path = self.templates_dir / phase_dir / f"{scope}.md"

        if not template_path.exists():
            raise FileNotFoundError(
                f"Template not found: {template_path}."
                f"Expected template for scope '{scope}' in phase '{phase_dir}'"
            )
        
        return template_path


    def standards_bundle_for(self, context: dict[str, Any]) -> str:
        """
        Generate standards bundle content for this profile.
        
        Uses layer-based standards mapping from config.yml.
        Standards are deduplicated and concatenated with separators.
        
        Args:
            context: Workflow context containing 'scope'
            
        Returns:
            Standards bundle content as a string
            
        Raises:
            ValueError: If scope not found or standards files missing
        """
        scope = context.get("scope", "domain")

        # Validate scope
        if scope not in self.config["scopes"]:
            available = list(self.config["scopes"].keys())
            raise ValueError(f"Invalid scope '{scope}'. Available: {available}")

        # Get layers for this scope
        layers = self.config["scopes"][scope]["layers"]

        # Collect unique standards files (set automatically deduplciates)
        standards_files = set()

        # Add universal standards first
        if "_universal" in self.config["layer_standards"]:
            standards_files.update(self.config["layer_standards"]["_universal"])

        # Add layer-specific standards
        for layer in layers:
            if layer in self.config["layer_standards"]:
                standards_files.update(self.config["layer_standards"][layer])
            else:
                # Warn but continue (allows custom layers)
                logging.warning(
                    f"Layer '{layer}' in scope '{scope}' has no standards defined"
                )

        # Build bundle with separators
        return self._build_bundle(standards_files)

    def _build_bundle(self, standards_files: set[str]) -> str:
        """
        Build standards bundle from file list.
        
        Args:
            standards_files: Set of relative filenames
            
        Returns:
            Concatenated bundle with separators
        """
        bundle_parts = []

        for filename in sorted(standards_files):
            # Validate file exists and is within standards root
            filepath = validate_standards_file(filename, self.standards_root)

            # Add separator with source filename
            bundle_parts.append(f"--- {filename} ---\n\n")

            # Add file content
            content = filepath.read_text(encoding='utf-8')
            bundle_parts.append(content)
            bundle_parts.append("\n\n")

        return "".join(bundle_parts)

    def parse_bundle(self, content: str) -> dict[str, str]:
        """
        Parse AI-generated bundle into separate files.
        
        Expects bundle format:
        <<<FILE: Product.java>>>
            // 4-space indented code
            
        <<<FILE: ProductRepository.java>>>
            // 4-space indented code
        
        Args:
            content: The bundle content from AI response
            
        Returns:
            Dictionary mapping filenames to content
            
        Raises:
            ValueError: If bundle format is invalid
        """

        files = {}
        current_file = None
        current_content = []

        for line in content.split("\n"):
            # Check for file marker
            match = re.match(r"^<<<FILE:\s*(.+?)>>>$", line.strip())
            if match:
                # Save previous file if exists
                if current_file:
                    # Dedent 4-space indentation
                    dedented = [
                        ln[4:] if ln.startswith("    ") else ln
                        for ln in current_content
                    ]
                    files[current_file] = "\n".join(dedented).strip()

                # Start new file
                current_file = match.group(1).strip()
                current_content = []
            elif current_file:
                # Accumulate content for current file
                current_content.append(line)

        # Save last file
        if current_file:
            dedented = [
                ln[4:] if ln.startswith("    ") else ln
                for ln in current_content
            ]
            files[current_file] = "\n".join(dedented).strip()

        if not files:
            raise ValueError(
                "No files found in bundle. Expected format:\n"
                "<<<FILE: filename.java>>>\n"
                "    code here (4-space indented)"
            )
        
        return files

    def artifact_dir_for(
            self,
            entity: str,
            scope: str = "domain",
            session_id: str | None = None,
            timestamp: str | None = None
    ) -> Path:
        """
        Get the output directory path for generated artifacts.
        
        Args:
            entity: The entity name (e.g., "Product")
            scope: The generation scope (e.g., "domain", "vertical")
            session_id: Session identifier (provided by engine)
            timestamp: ISO timestamp (provided by engine)
            
        Returns:
            Path where artifacts should be written
        """
        artifacts_config = self.config.get("artifacts", {})
        target_root = artifacts_config.get("target_root")

        if not target_root:
            # No target root - return relative path for session directory
            return Path("artifacts")
        
        # Resolve target root (allows relative paths)
        target_root_path = validate_target_root(target_root)

        # Get target structure pattern
        target_structure = artifacts_config.get("target_structure", "{entity}/{scope}")

        # Validate template variables
        allowed_vars = {"entity", "scope", "timestamp", "session_id"}
        PathValidator.validate_template_variables(target_structure, allowed_vars)
        PathValidator.validate_template_has_required(target_structure, {"entity"})

        # Generate safe defaults if not provided (for testing)
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

        if session_id is None:
            session_id = f"session{timestamp}"

        variables = {
            "entity": entity,
            "scope": scope,
            "timestamp": timestamp,
            "session_id": session_id
        }

        structure = PathValidator.format_template(
            target_structure,
            variables,
            sanitize=True
        )

        return target_root_path / structure

    def review_config_for(self) -> dict[str, Any]:
        """
        Get review configuration for this profile.
        
        Standards verification uses standards_bundle_for() - this just controls
        review behavior (severity, auto-fix, etc.)
        
        Returns:
            Dictionary with review behavior configuration
        """

        return {
            "severity": "strict",  # How strict: "strict", "normal", "lenient"
            "auto_fix": False,     # Whether to attempt automatic fixes
        }

    # -------------------------
    # Prompt generation methods
    # -------------------------

    _REQUIRED_CONTEXT_KEYS = {
        "TASK_ID",
        "DEV",
        "DATE",
        "ENTITY",
        "SCOPE",
        "TABLE",
        "BOUNDED_CONTEXT",
        "SESSION_ID",
        "PROFILE",
        "ITERATION",
    }

    def _validate_prompt_context(self, context: dict[str, Any]) -> None:
        missing = self._REQUIRED_CONTEXT_KEYS - set(context.keys())
        if missing:
            raise KeyError(
                f"Missing required context keys: {sorted(missing)}. "
                f"Required: {sorted(self._REQUIRED_CONTEXT_KEYS)}"
            )

    def generate_planning_prompt(self, context: dict[str, Any]) -> str:
        from aiwf.domain.template_renderer import render_template
        self._validate_prompt_context(context)
        template_path = self.prompt_template_for(WorkflowPhase.INITIALIZED, context.get("scope", "domain"))
        return render_template(template_path, context, templates_root=self.templates_dir)

    def generate_generation_prompt(self, context: dict[str, Any]) -> str:
        from aiwf.domain.template_renderer import render_template
        self._validate_prompt_context(context)
        template_path = self.prompt_template_for(WorkflowPhase.PLANNED, context.get("scope", "domain"))
        return render_template(template_path, context, templates_root=self.templates_dir)

    def generate_review_prompt(self, context: dict[str, Any]) -> str:
        from aiwf.domain.template_renderer import render_template
        self._validate_prompt_context(context)
        template_path = self.prompt_template_for(WorkflowPhase.GENERATED, context.get("scope", "domain"))
        return render_template(template_path, context, templates_root=self.templates_dir)

    def generate_revision_prompt(self, context: dict[str, Any]) -> str:
        from aiwf.domain.template_renderer import render_template
        self._validate_prompt_context(context)
        template_path = self.prompt_template_for(WorkflowPhase.REVIEWED, context.get("scope", "domain"))
        return render_template(template_path, context, templates_root=self.templates_dir)

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.prompt_sections import PromptSections
from aiwf.domain.models.workflow_state import WorkflowPhase

# Type alias for prompt generation return type
# Profiles can return either a raw string (pass-through) or structured sections
PromptResult = str | PromptSections


class WorkflowProfile(ABC):
    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return profile metadata for discovery commands.

        Returns:
            dict with keys: name, description, target_stack, scopes, phases,
            requires_config, config_keys, context_schema
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "target_stack": "Unknown",
            "scopes": [],
            "phases": ["planning", "generation", "review", "revision"],
            "requires_config": False,
            "config_keys": [],
            "context_schema": {},  # Schema for validating context dict
            "can_regenerate_prompts": False,  # ADR-0015: Enable prompt regeneration on rejection
        }

    def validate_metadata(self, metadata: dict[str, Any] | None) -> None:
        """Validate metadata required by this profile.

        Called during workflow initialization. Profiles should override
        to check for required metadata fields.

        Args:
            metadata: Metadata dict from workflow init, may be None

        Raises:
            ValueError: If required metadata is missing or invalid
        """
        pass  # Default: no validation

    def get_default_standards_provider_key(self) -> str:
        """Return the default standards provider key for this profile.

        Used when no --standards-provider CLI option is specified.
        Profiles should override to specify their default provider.

        Returns:
            Registered standards provider key (e.g., "scoped-layer-fs")

        Raises:
            NotImplementedError: If profile does not override this method
        """
        raise NotImplementedError(
            "Profile must implement get_default_standards_provider_key()"
        )

    def get_standards_config(self) -> dict[str, Any]:
        """Return configuration dict for standards provider.

        This config is passed to StandardsProviderFactory.create().
        Profiles should override to return provider-specific settings.

        Returns:
            Configuration dict with provider-specific settings
        """
        return {}

    def regenerate_prompt(
        self,
        phase: WorkflowPhase,
        feedback: str,
        context: dict[str, Any],
    ) -> PromptResult:
        """Regenerate prompt based on rejection feedback.

        ADR-0015: Only called if get_metadata()["can_regenerate_prompts"] is True.
        Profiles that support prompt regeneration should override this method.

        Args:
            phase: Current workflow phase (PLAN, GENERATE, REVIEW, REVISE)
            feedback: Rejection feedback from the approver
            context: Template context with workflow metadata

        Returns:
            Regenerated prompt content as string or PromptSections

        Raises:
            NotImplementedError: If profile does not support prompt regeneration
        """
        raise NotImplementedError("Profile does not support prompt regeneration")

    @abstractmethod
    def generate_planning_prompt(self, context: dict) -> PromptResult:
        ...

    @abstractmethod
    def generate_generation_prompt(self, context: dict) -> PromptResult:
        """
        Generate code generation prompt content.

        Args:
            context: Template context with workflow metadata

        Returns:
            Prompt content as string or PromptSections

        Raises:
            KeyError: If required context keys missing
        """
        ...


    @abstractmethod
    def generate_review_prompt(self, context: dict) -> PromptResult:
        """
        Generate code review prompt content.

        Args:
            context: Template context with workflow metadata

        Returns:
            Prompt content as string or PromptSections
        """
        ...

    @abstractmethod
    def generate_revision_prompt(self, context: dict) -> PromptResult:
        """
        Generate code revision prompt content.

        Args:
            context: Template context with workflow metadata

        Returns:
            Prompt content as string or PromptSections
        """
        ...

    @abstractmethod
    def process_planning_response(self, content: str) -> ProcessingResult:
        """
        Process planning response and determine status.
        
        Args:
            content: Raw planning response content
        
        Returns:
            ProcessingResult with status and optional artifacts
        """
        ...

    @abstractmethod
    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        """
        Process generation response and determine status.

        Args:
            content: Raw generation response content
            session_dir: Path to the workflow session directory
            iteration: Current iteration number of the workflow session

        Returns:
            ProcessingResult with status and optional WritePlan.

        WritePlan Contract:
            Paths in WritePlan.writes should be filename-only or relative paths
            without iteration prefixes. The engine adds the canonical
            `iteration-{N}/code/` prefix when writing artifacts.

            Examples of valid paths:
            - "Customer.java" (filename only - preferred)
            - "entity/Customer.java" (relative with subdirectory)

            Legacy paths with iteration prefixes (e.g., "iteration-1/code/Customer.java")
            are normalized by the engine but should be avoided in new profiles.
        """
        ...

    @abstractmethod
    def process_review_response(self, content: str) -> ProcessingResult:
        """
        Process review response and determine status.
        Args:
            content: Raw review response content
        Returns:
            ProcessingResult with status and optional artifacts
        """
        ...

    @abstractmethod
    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        """
        Process revision response and determine status.

        Args:
            content: Raw revision response content
            session_dir: Path to the workflow session directory
            iteration: Current iteration number of the workflow session

        Returns:
            ProcessingResult with status and optional WritePlan.

        WritePlan Contract:
            Same as process_generation_response - paths should be filename-only
            or relative paths. The engine adds `iteration-{N}/code/` prefix.
        """
        ...

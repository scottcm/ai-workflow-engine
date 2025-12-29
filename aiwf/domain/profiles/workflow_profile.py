from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from aiwf.domain.models.processing_result import ProcessingResult


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

    @abstractmethod
    def generate_planning_prompt(self, context: dict) -> str:
        ...

    @abstractmethod
    def generate_generation_prompt(self, context: dict) -> str:
        """
        Generate code generation prompt content.
        
        Args:
            context: Template context with workflow metadata
        
        Returns:
            Prompt content as string
            
        Raises:
            KeyError: If required context keys missing
        """
        ...


    @abstractmethod
    def generate_review_prompt(self, context: dict) -> str:
        """
        Generate code review prompt content.
        Args:
            context: Template context with workflow metadata
        Returns:
            Prompt content as string
        """
        ...

    @abstractmethod
    def generate_revision_prompt(self, context: dict) -> str:
        """
        Generate code revision prompt content.
        Args:
            context: Template context with workflow metadata
        Returns:
            Prompt content as string
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
            content: Raw planning response content
            session_dir: Path to the workflow session directory
            iteration: Current iteration number of the workflow session
        
        Returns:
            ProcessingResult with status and optional artifacts
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
            ProcessingResult with status and optional artifacts
        """
        ...

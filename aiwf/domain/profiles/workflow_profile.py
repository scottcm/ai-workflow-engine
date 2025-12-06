from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from aiwf.domain.models.workflow_state import WorkflowPhase


class WorkflowProfile(ABC):
    """Abstract interface for workflow profiles (Strategy pattern)"""
    
    @abstractmethod
    def prompt_template_for(self, phase: WorkflowPhase) -> Path:
        """
        Get the path to the prompt template for the given phase.
        
        Args:
            phase: The workflow phase
            
        Returns:
            Path to the prompt template file
        """
        ...
    
    @abstractmethod
    def standards_bundle_for(self, context: dict[str, Any]) -> str:
        """
        Generate standards bundle content for this profile.
        
        Args:
            context: Workflow context (entity name, etc.)
            
        Returns:
            Standards bundle content as a string
        """
        ...
    
    @abstractmethod
    def parse_bundle(self, content: str) -> dict[str, str]:
        """
        Parse AI-generated bundle into separate files.
        
        Args:
            content: The bundle content from AI response
            
        Returns:
            Dictionary mapping filenames to content
        """
        ...
    
    @abstractmethod
    def artifact_dir_for(self, entity: str) -> Path:
        """
        Get the output directory path for generated artifacts.
        
        Args:
            entity: The entity name (e.g., "Product")
            
        Returns:
            Path where artifacts should be written
        """
        ...
    
    @abstractmethod
    def review_config_for(self) -> dict[str, Any]:
        """
        Get review configuration for this profile.
        
        Returns:
            Dictionary with review rules and criteria
        """
        ...
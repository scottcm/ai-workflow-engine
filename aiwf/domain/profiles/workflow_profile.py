from abc import ABC, abstractmethod
from pathlib import Path

from aiwf.domain.models.processing_result import ProcessingResult


class WorkflowProfile(ABC):
    @abstractmethod
    def generate_planning_prompt(self, context: dict) -> str:
        """
        Generate planning prompt content.
        
        Args:
            context: Template context containing workflow metadata
                    (entity, table, scope, session_id, etc.)
        
        Returns:
            Prompt content as string (typically Markdown format)
            
        Raises:
            KeyError: If required context keys missing
        """
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

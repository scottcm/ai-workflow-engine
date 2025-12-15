from abc import ABC, abstractmethod
from pathlib import Path

from aiwf.domain.models.processing_result import ProcessingResult


class WorkflowProfile(ABC):
    @abstractmethod
    def generate_planning_prompt(self, context: dict) -> str:
        ...

    @abstractmethod
    def generate_generation_prompt(self, context: dict) -> str:
        ...

    @abstractmethod
    def generate_review_prompt(self, context: dict) -> str:
        ...

    @abstractmethod
    def generate_revision_prompt(self, context: dict) -> str:
        ...

    @abstractmethod
    def process_planning_response(self, content: str) -> ProcessingResult:
        ...

    @abstractmethod
    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        ...

    @abstractmethod
    def process_review_response(self, content: str) -> ProcessingResult:
        ...

    @abstractmethod
    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        ...

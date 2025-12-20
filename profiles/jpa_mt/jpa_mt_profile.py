from pathlib import Path
from typing import Any

from aiwf.domain.profiles.workflow_profile import WorkflowProfile
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.application.standards_provider import FileBasedStandardsProvider, StandardsProvider
from profiles.jpa_mt.jpa_mt_config import JpaMtConfig


class JpaMtProfile(WorkflowProfile):
    def __init__(self, **config):
        model = JpaMtConfig.model_validate(config)
        self.config = model.model_dump()
    
    def get_standards_provider(self) -> StandardsProvider:
        """Return FileBasedStandardsProvider configured for JPA-MT."""
        standards_root = Path(self.config['standards']['root'])
        
        # Collect standards files for scope
        # For now, just collect all standards from all layers
        # (Later slices will make this scope-aware)
        standards_files: list[str] = []
        for layer, files in self.config['layer_standards'].items():
            if layer != '_universal':
                standards_files.extend(files)
        
        # Add universal standards
        if '_universal' in self.config['layer_standards']:
            standards_files.extend(self.config['layer_standards']['_universal'])
        
        return FileBasedStandardsProvider(
            standards_root=standards_root,
            standards_files=standards_files
        )
    
    def generate_planning_prompt(self, context: dict) -> str:
        # TODO: Implement in later slice
        raise NotImplementedError("Planning prompt generation not yet implemented")
    
    def generate_generation_prompt(self, context: dict) -> str:
        # TODO: Implement in later slice
        raise NotImplementedError("Generation prompt generation not yet implemented")
    
    def generate_review_prompt(self, context: dict) -> str:
        # TODO: Implement in later slice
        raise NotImplementedError("Review prompt generation not yet implemented")
    
    def generate_revision_prompt(self, context: dict) -> str:
        # TODO: Implement in later slice
        raise NotImplementedError("Revision prompt generation not yet implemented")
    
    def process_planning_response(self, content: str) -> ProcessingResult:
        # TODO: Implement in later slice
        raise NotImplementedError("Planning response processing not yet implemented")
    
    def process_generation_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        # TODO: Implement in later slice
        raise NotImplementedError("Generation response processing not yet implemented")
    
    def process_review_response(self, content: str) -> ProcessingResult:
        # TODO: Implement in later slice
        raise NotImplementedError("Review response processing not yet implemented")
    
    def process_revision_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        # TODO: Implement in later slice
        raise NotImplementedError("Revision response processing not yet implemented")
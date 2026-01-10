"""PromptService - centralized prompt generation and assembly.

Phase 4 of orchestrator modularization: centralizes profile prompt
dispatch and PromptAssembler invocation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState
from aiwf.domain.profiles.profile_factory import ProfileFactory


@dataclass
class PromptGenerationResult:
    """Result from prompt generation.

    Contains the assembled prompt and file metadata.
    """

    # Assembled prompt content ready to write
    user_prompt: str

    # Filename for the prompt file (e.g., "planning-prompt.md")
    prompt_filename: str

    # Filename for the response file (e.g., "planning-response.md")
    response_filename: str


class PromptService:
    """Service for generating and assembling prompts.

    Centralizes:
    - Profile prompt generation dispatch
    - PromptAssembler invocation
    - Path calculation for prompt/response files
    """

    def generate_prompt(
        self,
        state: WorkflowState,
        session_dir: Path,
        phase_files: dict[WorkflowPhase, tuple[str, str]],
        context: dict[str, Any],
    ) -> PromptGenerationResult:
        """Generate assembled prompt for current phase.

        Dispatches to the appropriate profile method based on phase,
        then assembles the prompt with engine variables.

        Args:
            state: Current workflow state
            session_dir: Session directory path
            phase_files: Phase to (prompt_filename, response_filename) mapping
            context: Context dict for profile prompt generation

        Returns:
            PromptGenerationResult with assembled prompt and filenames

        Raises:
            ValueError: If no prompt generation for the current phase
        """
        from aiwf.application.prompt_assembler import PromptAssembler

        # Get filenames
        prompt_filename, response_filename = phase_files[state.phase]

        # Add filenames to context for profile
        context["prompt_filename"] = prompt_filename
        context["response_filename"] = response_filename

        # Get profile and dispatch to appropriate method
        profile = ProfileFactory.create(state.profile)

        phase_prompt_methods = {
            WorkflowPhase.PLAN: profile.generate_planning_prompt,
            WorkflowPhase.GENERATE: profile.generate_generation_prompt,
            WorkflowPhase.REVIEW: profile.generate_review_prompt,
            WorkflowPhase.REVISE: profile.generate_revision_prompt,
        }

        if state.phase not in phase_prompt_methods:
            raise ValueError(f"No prompt generation for phase: {state.phase}")

        profile_prompt = phase_prompt_methods[state.phase](context)

        # Calculate response path for output instructions
        response_relpath = f"iteration-{state.current_iteration}/{response_filename}"

        # Assemble prompt
        assembler = PromptAssembler(session_dir, state)
        assembled = assembler.assemble(
            profile_prompt,
            fs_ability="local-write",
            response_relpath=response_relpath,
        )

        return PromptGenerationResult(
            user_prompt=assembled["user_prompt"],
            prompt_filename=prompt_filename,
            response_filename=response_filename,
        )

    def assemble_prompt(
        self,
        prompt_content: str,
        state: WorkflowState,
        session_dir: Path,
        response_relpath: str,
    ) -> str:
        """Assemble prompt content with engine variables and output instructions.

        Used for regenerated prompts where the profile has already generated
        the content but it needs assembly.

        Args:
            prompt_content: Raw prompt string
            state: Current workflow state
            session_dir: Session directory path
            response_relpath: Relative path for response file

        Returns:
            Assembled prompt string
        """
        # Profile always returns strings for regenerated prompts
        return prompt_content
"""Prompt assembly module for engine variable substitution and output instructions."""

from pathlib import Path

from aiwf.domain.models.workflow_state import WorkflowState


class PromptAssembler:
    """Assembles final prompts by resolving engine variables and adding output instructions.

    Engine responsibilities (per ADR-0011):
    - Substitute engine-owned variables ({{STANDARDS}}, {{PLAN}})
    - Append output instructions based on fs_ability

    Profile responsibilities:
    - Complete prompt content including artifact references
    - Domain-specific formatting and structure
    """

    def __init__(self, session_dir: Path, state: WorkflowState):
        self.session_dir = session_dir
        self.state = state

    def _get_engine_variables(self) -> dict[str, str]:
        """Build engine-owned variables with workspace-relative paths.

        Returns:
            Dict mapping variable names to workspace-relative file paths.
        """
        session_path = f".aiwf/sessions/{self.state.session_id}"
        return {
            "{{STANDARDS}}": f"{session_path}/standards-bundle.md",
            "{{PLAN}}": f"{session_path}/plan.md",
        }

    def assemble(
        self,
        profile_prompt: str,
        fs_ability: str,
        response_relpath: str | None = None,
    ) -> dict[str, str]:
        """Assemble the final prompt.

        Args:
            profile_prompt: The complete prompt content from the profile
            fs_ability: Provider's filesystem capability (local-write, local-read, write-only, none)
            response_relpath: Path where response should be saved (e.g., "iteration-1/planning-response.md")

        Returns:
            dict with keys:
            - "user_prompt": The assembled prompt content
            - "system_prompt": Empty string (reserved for future use)
        """
        # 1. Substitute engine-owned variables
        prompt = self._substitute_engine_variables(profile_prompt)

        # 2. Append output instructions
        output_instructions = self._build_output_instructions(fs_ability, response_relpath)
        if output_instructions:
            prompt = prompt + "\n\n---\n\n" + output_instructions

        return {
            "system_prompt": "",
            "user_prompt": prompt,
        }

    def _substitute_engine_variables(self, content: str) -> str:
        """Substitute engine-owned variables in prompt content.

        Variables are replaced with workspace-relative paths so the AI
        can locate files regardless of its working directory context.
        """
        result = content
        for variable, value in self._get_engine_variables().items():
            result = result.replace(variable, value)
        return result

    def _build_output_instructions(
        self, fs_ability: str, response_relpath: str | None
    ) -> str:
        """Build output instructions based on fs_ability.

        Args:
            fs_ability: Provider's filesystem capability
            response_relpath: Path where response should be saved

        Returns:
            Output instructions string, or empty string if no instructions needed
        """
        if not response_relpath:
            return ""

        response_filename = Path(response_relpath).name

        if fs_ability == "local-write":
            # Use absolute path to avoid working directory ambiguity
            absolute_path = self.session_dir / response_relpath
            return f"## Output Destination\n\nDo not display the file contents to the screen.\nSave your response to `{absolute_path}`"
        elif fs_ability == "local-read":
            return f"## Output Destination\n\nName your output file `{response_filename}`"
        elif fs_ability == "write-only":
            return f"## Output Destination\n\nCreate a downloadable file named `{response_filename}`"
        else:  # none or unknown
            return ""
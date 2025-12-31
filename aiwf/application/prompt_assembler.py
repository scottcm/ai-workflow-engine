"""Prompt assembly module for combining session artifacts, profile content, and output instructions."""

from pathlib import Path

from aiwf.application.prompt_builder import PromptBuilder
from aiwf.domain.models.prompt_sections import PromptSections
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState
from aiwf.domain.profiles.workflow_profile import PromptResult


class PromptAssembler:
    """Assembles final prompts from session artifacts, profile content, and engine instructions.

    Supports two modes (Strategy pattern):
    - Pass-through: profile returns string, engine appends artifacts and output instructions
    - Structured: profile returns PromptSections, engine uses PromptBuilder
    """

    def __init__(self, session_dir: Path, state: WorkflowState):
        self.session_dir = session_dir
        self.state = state

    def assemble(
        self,
        profile_prompt: PromptResult,
        fs_ability: str,
        response_relpath: str | None = None,
        supports_system_prompt: bool = False,
        supports_file_attachments: bool = False,
    ) -> dict[str, str]:
        """Assemble the final prompt.

        Args:
            profile_prompt: The prompt content from the profile (str or PromptSections)
            fs_ability: Provider's filesystem capability
            response_relpath: Path where response should be saved (e.g., "iteration-1/generation-response.md")
            supports_system_prompt: Whether provider supports system prompts
            supports_file_attachments: Whether provider supports file attachments

        Returns:
            dict with keys:
            - "user_prompt": The main prompt content
            - "system_prompt": System instructions (if supports_system_prompt)
        """
        # Strategy: route based on profile_prompt type
        if isinstance(profile_prompt, PromptSections):
            return self._assemble_from_sections(
                profile_prompt,
                fs_ability,
                response_relpath,
                supports_system_prompt,
                supports_file_attachments,
            )
        else:
            return self._assemble_from_string(
                profile_prompt,
                fs_ability,
                response_relpath,
                supports_system_prompt,
                supports_file_attachments,
            )

    def _assemble_from_sections(
        self,
        sections: PromptSections,
        fs_ability: str,
        response_relpath: str | None,
        supports_system_prompt: bool,
        supports_file_attachments: bool,
    ) -> dict[str, str]:
        """Assemble prompt from structured PromptSections using PromptBuilder."""
        # Build session artifacts as dict for merging with required_inputs
        session_artifacts = self._build_session_artifacts_dict(supports_file_attachments)

        # Use PromptBuilder
        builder = PromptBuilder.from_sections(sections)
        builder.with_session_artifacts(session_artifacts)

        # Build the prompt
        result = builder.build(supports_system_prompt=supports_system_prompt)

        # Add output instructions
        output_instructions = self._build_output_instructions(fs_ability, response_relpath)
        if output_instructions:
            if supports_system_prompt:
                # Append to system prompt
                if result["system_prompt"]:
                    result["system_prompt"] = result["system_prompt"] + "\n\n" + output_instructions
                else:
                    result["system_prompt"] = output_instructions
            else:
                # Append to user prompt
                result["user_prompt"] = result["user_prompt"] + "\n\n" + output_instructions

        return result

    def _assemble_from_string(
        self,
        profile_prompt: str,
        fs_ability: str,
        response_relpath: str | None,
        supports_system_prompt: bool,
        supports_file_attachments: bool,
    ) -> dict[str, str]:
        """Assemble prompt from raw string (pass-through mode)."""
        # 1. Build session artifacts section
        artifacts = self._build_session_artifacts(supports_file_attachments)

        # 2. Build output instructions
        output_instructions = self._build_output_instructions(fs_ability, response_relpath)

        # 3. Combine based on provider capabilities
        if supports_system_prompt and output_instructions:
            # When system prompt is supported, put output instructions there
            user_parts = []
            if artifacts:
                user_parts.append(artifacts)
            user_parts.append(profile_prompt)
            user_prompt = "\n\n---\n\n".join(user_parts)
            return {
                "system_prompt": output_instructions,
                "user_prompt": user_prompt,
            }
        else:
            # Without system prompt support, combine everything into user_prompt
            user_parts = []
            if artifacts:
                user_parts.append(artifacts)
            user_parts.append(profile_prompt)
            if output_instructions:
                user_parts.append(output_instructions)
            user_prompt = "\n\n---\n\n".join(user_parts)
            return {
                "system_prompt": "",
                "user_prompt": user_prompt,
            }

    def _build_session_artifacts_dict(self, use_file_refs: bool) -> dict[str, str]:
        """Build session artifacts as a dict for merging with PromptSections.required_inputs."""
        artifacts = {}

        # Standards bundle (for all phases except INITIALIZED)
        if self.state.phase != WorkflowPhase.INIT:
            standards_content = self._get_artifact_content("standards-bundle.md", use_file_refs)
            if standards_content:
                artifacts["standards-bundle.md"] = f"Coding standards\n\n{standards_content}"

        # Plan (for generation, review, revision phases)
        if self.state.phase in (
            WorkflowPhase.GENERATE,
            WorkflowPhase.REVIEW,
            WorkflowPhase.REVISE,
        ):
            plan_content = self._get_artifact_content("plan.md", use_file_refs)
            if plan_content:
                artifacts["plan.md"] = f"Approved implementation plan\n\n{plan_content}"

        return artifacts

    def _build_session_artifacts(self, use_file_refs: bool) -> str:
        """Build the session artifacts section."""
        sections = []

        # Standards bundle (for all phases except INITIALIZED)
        if self.state.phase != WorkflowPhase.INIT:
            standards_content = self._get_artifact_content(
                "standards-bundle.md", use_file_refs
            )
            if standards_content:
                sections.append(f"## Standards Bundle\n\n{standards_content}")

        # Plan (for generation, review, revision phases)
        if self.state.phase in (
            WorkflowPhase.GENERATE,
            WorkflowPhase.REVIEW,
            WorkflowPhase.REVISE,
        ):
            plan_content = self._get_artifact_content("plan.md", use_file_refs)
            if plan_content:
                sections.append(f"## Approved Plan\n\n{plan_content}")

        # Previous code (for review and revision phases)
        if self.state.phase in (WorkflowPhase.REVIEW, WorkflowPhase.REVISE):
            code_section = self._build_code_section(use_file_refs)
            if code_section:
                sections.append(code_section)

        return "\n\n---\n\n".join(sections)

    def _get_artifact_content(self, filename: str, use_file_refs: bool) -> str:
        """Get artifact content, either as file reference or inline."""
        path = self.session_dir / filename
        if not path.exists():
            return ""

        if use_file_refs:
            return f"@{path}"
        else:
            return path.read_text(encoding="utf-8")

    def _build_code_section(self, use_file_refs: bool) -> str:
        """Build the previous code section for review/revision."""
        # Determine which iteration's code to include
        if self.state.phase == WorkflowPhase.REVIEW:
            code_iteration = self.state.current_iteration
        else:  # REVISE - code is from previous iteration
            # Guard: REVISE should only occur in iteration 2+
            if self.state.current_iteration <= 1:
                return ""  # No previous iteration to revise
            code_iteration = self.state.current_iteration - 1

        code_dir = self.session_dir / f"iteration-{code_iteration}" / "code"
        if not code_dir.exists():
            return ""

        sections = ["## Previous Code"]
        for file_path in sorted(code_dir.rglob("*")):
            if file_path.is_file():
                filename = file_path.name
                if use_file_refs:
                    sections.append(f"### {filename}\n\n@{file_path}")
                else:
                    content = file_path.read_text(encoding="utf-8")
                    # Detect language for syntax highlighting
                    lang = self._detect_language(filename)
                    sections.append(f"### {filename}\n\n```{lang}\n{content}\n```")

        return "\n\n".join(sections)

    def _detect_language(self, filename: str) -> str:
        """Detect language from filename for syntax highlighting."""
        ext_map = {
            ".java": "java",
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".md": "markdown",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".sql": "sql",
        }
        ext = Path(filename).suffix.lower()
        return ext_map.get(ext, "")

    def _build_output_instructions(
        self, fs_ability: str, response_relpath: str | None
    ) -> str:
        """Build output instructions based on fs_ability.

        Args:
            fs_ability: Provider's filesystem capability
            response_relpath: Path where response should be saved (e.g., "iteration-1/generation-response.md")

        Returns:
            Output instructions string, or empty string if no instructions needed
        """
        if not response_relpath:
            return ""

        response_filename = Path(response_relpath).name

        if fs_ability == "local-write":
            return f"## Output\n\nSave your complete response to `{response_relpath}`"
        elif fs_ability == "local-read":
            return f"## Output\n\nName your output file `{response_filename}`"
        elif fs_ability == "write-only":
            return f"## Output\n\nCreate a downloadable file named `{response_filename}`"
        else:  # none or unknown
            return ""
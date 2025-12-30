"""Prompt builder for constructing prompts from structured sections.

Implements the Builder pattern for assembling prompts from PromptSections.
"""
from typing import Self

from aiwf.domain.models.prompt_sections import PromptSections


class PromptBuilder:
    """Builds prompt content from structured sections.

    Supports fluent interface for setting sections and builds
    user_prompt and system_prompt based on provider capabilities.
    """

    def __init__(self) -> None:
        self._role: str | None = None
        self._required_inputs: dict[str, str] = {}
        self._session_artifacts: dict[str, str] = {}
        self._context: str | None = None
        self._task: str | None = None
        self._constraints: str | None = None
        self._expected_outputs: list[str] = []
        self._output_format: str | None = None

    @classmethod
    def from_sections(cls, sections: PromptSections) -> Self:
        """Create a PromptBuilder populated from a PromptSections model.

        Args:
            sections: PromptSections model with prompt content

        Returns:
            PromptBuilder with all fields populated from sections
        """
        builder = cls()
        builder.with_role(sections.role)
        builder.with_required_inputs(sections.required_inputs)
        builder.with_context(sections.context)
        builder.with_task(sections.task)
        builder.with_constraints(sections.constraints)
        builder.with_expected_outputs(sections.expected_outputs)
        builder.with_output_format(sections.output_format)
        return builder

    def with_role(self, role: str | None) -> Self:
        """Set the role section."""
        self._role = role
        return self

    def with_required_inputs(self, inputs: dict[str, str]) -> Self:
        """Set the required inputs from the profile."""
        self._required_inputs = inputs.copy() if inputs else {}
        return self

    def with_session_artifacts(self, artifacts: dict[str, str]) -> Self:
        """Set session artifacts to merge with required inputs.

        Session artifacts are merged with required inputs, but profile
        inputs take precedence over session artifacts.
        """
        self._session_artifacts = artifacts.copy() if artifacts else {}
        return self

    def with_context(self, context: str | None) -> Self:
        """Set the context section."""
        self._context = context
        return self

    def with_task(self, task: str | None) -> Self:
        """Set the task section (required)."""
        self._task = task
        return self

    def with_constraints(self, constraints: str | None) -> Self:
        """Set the constraints section."""
        self._constraints = constraints
        return self

    def with_expected_outputs(self, outputs: list[str]) -> Self:
        """Set the expected outputs list."""
        self._expected_outputs = list(outputs) if outputs else []
        return self

    def with_output_format(self, output_format: str | None) -> Self:
        """Set the output format section."""
        self._output_format = output_format
        return self

    def build(self, supports_system_prompt: bool = False) -> dict[str, str]:
        """Build the final prompt.

        Args:
            supports_system_prompt: Whether to separate role/constraints into system_prompt

        Returns:
            dict with keys:
            - "user_prompt": The main prompt content
            - "system_prompt": System instructions (role + constraints if supported)
        """
        if supports_system_prompt:
            return self._build_with_system_separation()
        else:
            return self._build_combined()

    def _build_combined(self) -> dict[str, str]:
        """Build with all sections in user_prompt."""
        sections = []

        # Build sections in canonical order
        if self._role:
            sections.append(f"## Role\n\n{self._role}")

        inputs_section = self._render_required_inputs()
        if inputs_section:
            sections.append(inputs_section)

        if self._context:
            sections.append(f"## Context\n\n{self._context}")

        if self._task:
            sections.append(f"## Task\n\n{self._task}")

        if self._constraints:
            sections.append(f"## Constraints\n\n{self._constraints}")

        if self._expected_outputs:
            sections.append(self._render_expected_outputs())

        if self._output_format:
            sections.append(f"## Output Format\n\n{self._output_format}")

        return {
            "system_prompt": "",
            "user_prompt": "\n\n".join(sections),
        }

    def _build_with_system_separation(self) -> dict[str, str]:
        """Build with role/constraints in system_prompt."""
        system_sections = []
        user_sections = []

        # System sections: role + constraints
        if self._role:
            system_sections.append(f"## Role\n\n{self._role}")

        if self._constraints:
            system_sections.append(f"## Constraints\n\n{self._constraints}")

        # User sections: everything else in canonical order
        inputs_section = self._render_required_inputs()
        if inputs_section:
            user_sections.append(inputs_section)

        if self._context:
            user_sections.append(f"## Context\n\n{self._context}")

        if self._task:
            user_sections.append(f"## Task\n\n{self._task}")

        if self._expected_outputs:
            user_sections.append(self._render_expected_outputs())

        if self._output_format:
            user_sections.append(f"## Output Format\n\n{self._output_format}")

        return {
            "system_prompt": "\n\n".join(system_sections),
            "user_prompt": "\n\n".join(user_sections),
        }

    def _render_required_inputs(self) -> str:
        """Render required inputs as bulleted list."""
        # Merge session artifacts with profile inputs (profile takes precedence)
        merged = {**self._session_artifacts, **self._required_inputs}

        if not merged:
            return ""

        lines = ["## Required Inputs", ""]
        for filename, description in sorted(merged.items()):
            lines.append(f"- **{filename}**: {description}")

        return "\n".join(lines)

    def _render_expected_outputs(self) -> str:
        """Render expected outputs as bulleted list."""
        if not self._expected_outputs:
            return ""

        lines = ["## Expected Outputs", ""]
        for output_path in self._expected_outputs:
            lines.append(f"- {output_path}")

        return "\n".join(lines)
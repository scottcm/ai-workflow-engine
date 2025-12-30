"""Prompt sections model for structured prompt building."""

from pydantic import BaseModel, Field


class PromptSections(BaseModel):
    """Structured prompt sections for system/user prompt separation.

    Profiles can return this instead of a raw string to enable:
    - System prompt separation when providers support it
    - Engine validation of required sections
    - Consistent prompt structure
    """

    role: str | None = None
    required_inputs: dict[str, str] = Field(default_factory=dict)
    context: str | None = None
    task: str  # Required field
    constraints: str | None = None
    expected_outputs: list[str] = Field(default_factory=list)
    output_format: str | None = None

    def get_system_sections(self) -> dict[str, str | None]:
        """Return sections suitable for system prompt.

        Returns role and constraints - behavioral content that defines
        who the AI is and what rules it must follow.
        """
        return {
            "role": self.role,
            "constraints": self.constraints,
        }

    def get_user_sections(self) -> dict[str, str | list[str] | dict[str, str] | None]:
        """Return sections suitable for user prompt.

        Returns context, task, expected_outputs, and output_format -
        the actual work to be done.
        """
        return {
            "context": self.context,
            "task": self.task,
            "expected_outputs": self.expected_outputs,
            "output_format": self.output_format,
        }
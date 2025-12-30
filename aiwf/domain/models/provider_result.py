"""Provider result model for AI provider responses."""

from pydantic import BaseModel, Field


class ProviderResult(BaseModel):
    """Result from AI provider execution.

    Supports multiple output files with flexible handling:
    - files dict keys are paths relative to /code directory
    - Value is file content (string) or None if provider wrote directly
    - Engine writes files where content is provided, validates existence where None
    """

    files: dict[str, str | None] = Field(default_factory=dict)
    response: str | None = None  # Optional commentary for response file
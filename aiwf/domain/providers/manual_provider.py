from typing import Any

from .ai_provider import AIProvider


class ManualProvider(AIProvider):
    """Human-in-the-loop provider (prompts written to disk)."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return manual provider metadata for discovery commands."""
        return {
            "name": "manual",
            "description": "Human-in-the-loop (prompts written to disk)",
            "requires_config": False,
            "config_keys": [],
        }

    async def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        """Manual provider does not generate responses automatically.

        Returns None/empty to signal that the response file should be
        created by the human operator.
        """
        # Return empty string - manual workflow expects user to write response file
        return ""

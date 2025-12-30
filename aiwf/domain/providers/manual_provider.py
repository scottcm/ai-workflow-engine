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
            "default_connection_timeout": None,  # No timeout for manual
            "default_response_timeout": None,
            # ManualProvider: no inherent capability, user specifies via CLI/config
            "fs_ability": None,  # Must be specified by user or use default
            "supports_system_prompt": False,
            "supports_file_attachments": False,
        }

    def validate(self) -> None:
        """Manual provider has no external dependencies to validate."""
        pass

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        """Manual provider does not generate responses automatically.

        Returns None to signal that the response file should be
        created by the human operator.
        """
        return None
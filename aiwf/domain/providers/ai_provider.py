from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Abstract interface for AI providers (Strategy pattern)."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with keys: name, description, requires_config, config_keys,
                           default_connection_timeout, default_response_timeout
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,  # seconds
            "default_response_timeout": 300,  # 5 minutes
        }

    @abstractmethod
    def validate(self) -> None:
        """Verify provider is accessible and configured correctly.

        Called at init time before workflow execution begins.
        Implementations should check API keys, connectivity, etc.

        Raises:
            ProviderError: If provider is misconfigured or unreachable
        """
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        """Generate AI response for the given prompt.

        Args:
            prompt: The prompt text to send to the AI
            context: Optional context dictionary (metadata, settings, etc.)
            connection_timeout: Timeout for establishing connection (None = use default)
            response_timeout: Timeout for receiving response (None = use default)

        Returns:
            Response string, or None for ManualProvider (signals user provides response)

        Raises:
            ProviderError: If the provider call fails (network, auth, timeout, etc.)
        """
        ...
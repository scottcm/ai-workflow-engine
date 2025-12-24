from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Abstract interface for AI providers (Strategy pattern)"""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with keys: name, description, requires_config, config_keys
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
        }

    @abstractmethod
    async def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        """
        Generate AI response for the given prompt.
        
        Args:
            prompt: The prompt text to send to the AI
            context: Optional context dictionary (metadata, settings, etc.)
            
        Returns:
            The AI's response as a string
            
        Raises:
            ProviderError: If the provider call fails
        """
        ...
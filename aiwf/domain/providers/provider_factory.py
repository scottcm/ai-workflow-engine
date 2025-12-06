from typing import Any
from .ai_provider import AIProvider

class ProviderFactory:
    """Factory for creating AI provider instances (Factory pattern)"""

    _registry: dict[str, type[AIProvider]] = {}

    @classmethod
    def register(cls, key: str, provider_class: type[AIProvider]) -> None:
        """
        Register a provider implementation.
        
        Args:
            key: Provider identifier (e.g., "claude", "gemini", "manual")
            provider_class: The provider class to register
        """
        cls._registry[key] = provider_class

    @classmethod
    def create(cls, provider_key: str, config: dict[str, Any] | None = None) -> AIProvider:
        """
        Create a provider instance.
        
        Args:
            provider_key: Registered provider identifier
            config: Optional configuration for the provider
            
        Returns:
            Instantiated AIProvider
            
        Raises:
            KeyError: If provider_key is not registered
        """
        if provider_key not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise KeyError(
                f"Provider: '{provider_key}' not found. "
                f"Available providers: {available}"
            )

        provider_class = cls._registry[provider_key]
        config = config or {}
        return provider_class(**config)
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """
        Get list of registered provider keys.
        
        Returns:
            List of registered provider identifiers
        """
        return list(cls._registry.keys())
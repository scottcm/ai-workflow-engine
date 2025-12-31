from typing import Any
from .response_provider import ResponseProvider


class ProviderFactory:
    """Factory for creating response provider instances (Factory pattern).

    Response providers generate responses to prompts. They may call AI APIs
    or signal manual mode where the user provides the response.
    """

    _registry: dict[str, type[ResponseProvider]] = {}

    @classmethod
    def register(cls, key: str, provider_class: type[ResponseProvider]) -> None:
        """
        Register a provider implementation.

        Args:
            key: Provider identifier (e.g., "claude", "gemini", "manual")
            provider_class: The provider class to register
        """
        cls._registry[key] = provider_class

    @classmethod
    def create(cls, provider_key: str, config: dict[str, Any] | None = None) -> ResponseProvider:
        """
        Create a provider instance.

        Args:
            provider_key: Registered provider identifier
            config: Optional configuration for the provider

        Returns:
            Instantiated ResponseProvider

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

    @classmethod
    def get_all_metadata(cls) -> list[dict[str, Any]]:
        """
        Get metadata for all registered providers.

        Returns:
            List of metadata dicts from each registered provider
        """
        return [
            provider_class.get_metadata()
            for provider_class in cls._registry.values()
        ]

    @classmethod
    def get_metadata(cls, provider_key: str) -> dict[str, Any] | None:
        """
        Get metadata for a specific provider.

        Args:
            provider_key: Registered provider identifier

        Returns:
            Metadata dict if found, None otherwise
        """
        if provider_key not in cls._registry:
            return None
        return cls._registry[provider_key].get_metadata()
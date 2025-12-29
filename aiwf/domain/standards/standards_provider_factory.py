"""Factory for creating standards provider instances (Factory pattern)."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StandardsProvider(Protocol):
    """Protocol for standards bundle providers.

    Implementations retrieve standards from various sources:
    - File-based (ScopedLayerFsProvider)
    - RAG/vector database
    - REST API
    - Database
    """

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with keys: name, description, requires_config, config_keys,
                           default_connection_timeout, default_response_timeout
        """
        ...

    def validate(self) -> None:
        """Verify provider is accessible and configured correctly.

        Called at init time before workflow execution begins.
        Implementations should check paths exist, connections work, etc.

        Raises:
            ProviderError: If provider is misconfigured or unreachable
        """
        ...

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Create standards bundle for the given context.

        Args:
            context: Workflow context (scope, entity, etc.)
            connection_timeout: Timeout for establishing connection/accessing path
            response_timeout: Timeout for reading/receiving all data

        Returns:
            Concatenated standards bundle as string

        Raises:
            ProviderError: If bundle creation fails or times out
            ValueError: If context is invalid (e.g., unknown scope)
        """
        ...


class StandardsProviderFactory:
    """Factory for creating standards provider instances.

    Follows the same pattern as ProviderFactory for AI providers.
    """

    _registry: dict[str, type[StandardsProvider]] = {}

    @classmethod
    def register(cls, key: str, provider_class: type[StandardsProvider]) -> None:
        """Register a standards provider class.

        Args:
            key: Unique identifier for the provider (e.g., "scoped-layer-fs")
            provider_class: Class implementing StandardsProvider protocol
        """
        cls._registry[key] = provider_class

    @classmethod
    def create(
        cls, key: str, config: dict[str, Any] | None = None
    ) -> StandardsProvider:
        """Create a standards provider instance.

        Args:
            key: Registered provider key
            config: Optional configuration dict passed to provider constructor

        Returns:
            Configured StandardsProvider instance

        Raises:
            KeyError: If provider key is not registered
        """
        if key not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise KeyError(
                f"Standards provider '{key}' not registered. "
                f"Available providers: {available}"
            )

        provider_class = cls._registry[key]
        config = config or {}
        return provider_class(config)

    @classmethod
    def list_providers(cls) -> list[str]:
        """Return list of registered provider keys."""
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, key: str) -> bool:
        """Check if a provider key is registered."""
        return key in cls._registry

    @classmethod
    def get_all_metadata(cls) -> list[dict[str, Any]]:
        """Get metadata for all registered providers.

        Returns:
            List of metadata dicts from each registered provider
        """
        return [
            provider_class.get_metadata() for provider_class in cls._registry.values()
        ]

    @classmethod
    def get_metadata(cls, key: str) -> dict[str, Any] | None:
        """Get metadata for a specific provider.

        Args:
            key: Registered provider identifier

        Returns:
            Metadata dict if found, None otherwise
        """
        if key not in cls._registry:
            return None
        return cls._registry[key].get_metadata()
from typing import Any
from .workflow_profile import WorkflowProfile

class ProfileFactory:
    """Factory for creating workflow profile instances (Factory pattern)"""

    _registry: dict[str, type[WorkflowProfile]] = {}

    @classmethod
    def register(cls, key: str, profile_class: type[WorkflowProfile]) -> None:
        """
        Register a profile implementation.
        
        Args:
            key: Profile identifier (e.g., "jpa-mt-domain")
            profile_class: The profile class to register
        """
        cls._registry[key] = profile_class

    @classmethod
    def create(cls, profile_key: str, config: dict[str, Any] | None = None) -> WorkflowProfile:
        """
        Create a profile instance.
        
        Args:
            profile_key: Registered profile identifier
            config: Optional configuration for the profile
            
        Returns:
            Instantiated WorkflowProfile
            
        Raises:
            KeyError: If profile_key is not registered
        """
        if profile_key not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise KeyError(
                f"Profile: '{profile_key}' not found. "
                f"Available profiles: {available}"
            )
        
        profile_class = cls._registry[profile_key]
        config = config or {}
        return profile_class(**config)
    
    @classmethod
    def list_profiles(cls) -> list[str]:
        """
        Get list of registered profile keys.

        Returns:
            List of registered profile identifiers
        """
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, profile_key: str) -> bool:
        """
        Check if a profile is registered.

        Args:
            profile_key: Profile identifier to check

        Returns:
            True if profile is registered, False otherwise
        """
        return profile_key in cls._registry

    @classmethod
    def get_all_metadata(cls) -> list[dict[str, Any]]:
        """
        Get metadata for all registered profiles.

        Returns:
            List of metadata dicts from each registered profile
        """
        return [
            profile_class.get_metadata()
            for profile_class in cls._registry.values()
        ]

    @classmethod
    def get_metadata(cls, profile_key: str) -> dict[str, Any] | None:
        """
        Get metadata for a specific profile.

        Args:
            profile_key: Registered profile identifier

        Returns:
            Metadata dict if found, None otherwise
        """
        if profile_key not in cls._registry:
            return None
        return cls._registry[profile_key].get_metadata()

    @classmethod
    def get(cls, name: str) -> type[WorkflowProfile] | None:
        """Get a registered profile class by name.

        Args:
            name: Profile identifier

        Returns:
            Profile class if registered, None otherwise
        """
        return cls._registry.get(name)

    @classmethod
    def clear(cls) -> None:
        """Clear registry (for testing)."""
        cls._registry.clear()

    @classmethod
    def snapshot(cls) -> dict[str, type[WorkflowProfile]]:
        """Capture current registry state for later restoration.

        Returns:
            Copy of the current registry dict.
        """
        return dict(cls._registry)

    @classmethod
    def restore(cls, snapshot: dict[str, type[WorkflowProfile]]) -> None:
        """Restore registry to a previously captured state.

        Args:
            snapshot: Registry state from a previous snapshot() call.
        """
        cls._registry.clear()
        cls._registry.update(snapshot)
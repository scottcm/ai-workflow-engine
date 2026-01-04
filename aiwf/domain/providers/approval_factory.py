"""Factory for creating approval providers.

ADR-0015: Registry pattern for approval provider instantiation.
"""

from typing import Any

from aiwf.domain.providers.approval_provider import (
    ApprovalProvider,
    SkipApprovalProvider,
    ManualApprovalProvider,
)
from aiwf.domain.providers.ai_approval_provider import AIApprovalProvider
from aiwf.domain.providers.provider_factory import AIProviderFactory


class ApprovalProviderFactory:
    """Factory for creating approval provider instances.

    Built-in providers:
    - "skip": SkipApprovalProvider (auto-approve)
    - "manual": ManualApprovalProvider (pause for user)

    Unknown keys are treated as AI provider keys and create
    AIApprovalProvider wrapping the corresponding AIProvider.
    """

    _registry: dict[str, type[ApprovalProvider]] = {
        "skip": SkipApprovalProvider,
        "manual": ManualApprovalProvider,
    }

    @classmethod
    def register(cls, key: str, provider_class: type[ApprovalProvider]) -> None:
        """Register a custom approval provider.

        Args:
            key: Provider identifier
            provider_class: ApprovalProvider subclass to register
        """
        cls._registry[key] = provider_class

    @classmethod
    def create(
        cls,
        key: str,
        config: dict[str, Any] | None = None,
    ) -> ApprovalProvider:
        """Create an approval provider instance.

        Args:
            key: Provider identifier ("skip", "manual", or response provider key)
            config: Optional configuration for response providers

        Returns:
            ApprovalProvider instance

        Raises:
            KeyError: If key is not a built-in and not a valid response provider
        """
        # Check built-in registry first
        if key in cls._registry:
            return cls._registry[key]()

        # Fall back to creating AIApprovalProvider wrapping an AI provider
        try:
            ai_provider = AIProviderFactory.create(key, config)

            # Validate fs_ability - approval providers must READ files to evaluate
            metadata = ai_provider.get_metadata()
            fs_ability = metadata.get("fs_ability", "none")

            if fs_ability in ("none", "write-only"):
                raise ValueError(
                    f"Provider {key!r} has fs_ability={fs_ability!r} and cannot be used for approval. "
                    f"Approval providers must be able to read files (fs_ability='local-read' or 'local-write') "
                    f"to evaluate artifacts. Use 'manual' for human approval."
                )

            return AIApprovalProvider(ai_provider=ai_provider)
        except KeyError:
            builtin_keys = list(cls._registry.keys())
            ai_keys = AIProviderFactory.list_providers()
            raise KeyError(
                f"Unknown approval provider: {key!r}. "
                f"Valid options: {builtin_keys} or any AIProvider: {ai_keys}"
            )

    @classmethod
    def list_providers(cls) -> list[str]:
        """Get list of available approval provider keys.

        Returns:
            List of built-in provider identifiers plus AI-wrapped providers.
        """
        builtin = list(cls._registry.keys())
        ai_providers = [
            f"{k} (via AI)" for k in AIProviderFactory.list_providers()
        ]
        return builtin + ai_providers

"""Factory for creating approval providers.

ADR-0012 Phase 4: Registry pattern for approval provider instantiation.
"""

from typing import Any

from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.skip_approver import SkipApprovalProvider
from aiwf.domain.providers.manual_approver import ManualApprovalProvider
from aiwf.domain.providers.ai_approver import AIApprovalProvider
from aiwf.domain.providers.provider_factory import ResponseProviderFactory


class ApprovalProviderFactory:
    """Factory for creating approval provider instances.

    Built-in providers:
    - "skip": SkipApprovalProvider (auto-approve)
    - "manual": ManualApprovalProvider (requires CLI command)

    Unknown keys are treated as response provider keys and create
    AIApprovalProvider wrapping the corresponding ResponseProvider.
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

        # Fall back to creating AIApprovalProvider with response provider
        response_provider = ResponseProviderFactory.create(key, config)
        return AIApprovalProvider(response_provider=response_provider)

    @classmethod
    def list_providers(cls) -> list[str]:
        """Get list of registered provider keys.

        Returns:
            List of built-in provider identifiers.
            Note: AI provider keys are not listed (delegated to ResponseProviderFactory).
        """
        return list(cls._registry.keys())
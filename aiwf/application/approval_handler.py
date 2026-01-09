"""Approval handler utilities.

ADR-0012: Chain of Responsibility handlers removed. TransitionTable handles state transitions.
This module retains run_provider() for AI provider invocation.

DEPRECATED: This module is deprecated and will be removed after orchestrator modularization
(Phase 3 of the refactor). Use ProviderExecutionService instead when available.
"""

import warnings

from aiwf.domain.providers.capabilities import ProviderCapabilities  # noqa: F401 - re-export for compatibility
from aiwf.domain.providers.provider_factory import AIProviderFactory


def run_provider(
    provider_key: str,
    prompt: str,
    system_prompt: str | None = None,
) -> str | None:
    """Invoke an AI provider to generate a response.

    .. deprecated::
        This function is deprecated and will be removed after orchestrator
        modularization (Phase 3). Use ProviderExecutionService instead.

    Args:
        provider_key: Registered provider key (e.g., "manual", "claude")
        prompt: The prompt text to send
        system_prompt: Optional system prompt for providers that support it

    Returns:
        Response string, or None if provider signals manual mode

    Raises:
        ProviderError: If provider fails (network, auth, timeout, etc.)
        KeyError: If provider_key is not registered
    """
    warnings.warn(
        "run_provider is deprecated and will be removed after orchestrator "
        "modularization Phase 3. Use ProviderExecutionService instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    provider = AIProviderFactory.create(provider_key)
    metadata = provider.get_metadata()
    connection_timeout = metadata.get("default_connection_timeout")
    response_timeout = metadata.get("default_response_timeout")

    return provider.generate(
        prompt,
        system_prompt=system_prompt,
        connection_timeout=connection_timeout,
        response_timeout=response_timeout,
    )
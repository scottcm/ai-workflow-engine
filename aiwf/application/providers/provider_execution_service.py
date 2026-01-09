"""ProviderExecutionService - centralized AI provider execution.

Phase 3 of orchestrator modularization: centralizes provider lookup,
metadata usage, timeouts, and response handling.
"""

from dataclasses import dataclass, field
from typing import Any

from aiwf.domain.errors import ProviderError
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.domain.providers.provider_factory import AIProviderFactory


@dataclass
class ProviderExecutionResult:
    """Normalized result from provider execution.

    Provides a consistent interface regardless of provider type:
    - awaiting_response=True: Provider didn't generate response (user provides externally)
    - awaiting_response=False: Provider generated response/files
    """

    # True if provider didn't generate a response (user provides externally)
    # This is provider-agnostic - workflow halts regardless of reason
    awaiting_response: bool = False

    # Response content (None if awaiting or if provider wrote directly)
    response: str | None = None

    # Files dict: path -> content (None means provider wrote directly)
    files: dict[str, str | None] = field(default_factory=dict)

    # Raw AIProviderResult if available
    raw_result: AIProviderResult | None = None


class ProviderExecutionService:
    """Service for executing AI providers.

    Centralizes:
    - Provider creation via factory
    - Timeout extraction from provider metadata
    - Response normalization
    """

    def execute(
        self,
        provider_key: str,
        prompt: str,
        *,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> ProviderExecutionResult:
        """Execute an AI provider and return normalized result.

        Args:
            provider_key: Registered provider key (e.g., "manual", "claude-code")
            prompt: The prompt text to send
            context: Optional context dict for provider
            system_prompt: Optional system prompt for providers that support it

        Returns:
            ProviderExecutionResult with normalized response

        Raises:
            ProviderError: If provider fails (network, auth, timeout, etc.)
            KeyError: If provider_key is not registered
        """
        provider = AIProviderFactory.create(provider_key)
        metadata = provider.get_metadata()

        # Extract timeouts from provider metadata
        connection_timeout = metadata.get("default_connection_timeout")
        response_timeout = metadata.get("default_response_timeout")

        # Execute provider
        response = provider.generate(
            prompt,
            context=context,
            system_prompt=system_prompt,
            connection_timeout=connection_timeout,
            response_timeout=response_timeout,
        )

        # Normalize result
        if response is None:
            # Provider didn't generate response - user provides externally
            return ProviderExecutionResult(awaiting_response=True)

        # AIProviderResult - normalize to our result type
        return ProviderExecutionResult(
            awaiting_response=False,
            response=response.response,
            files=response.files,
            raw_result=response,
        )

    def execute_simple(
        self,
        provider_key: str,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str | None:
        """Execute provider and return response string (legacy compatibility).

        This is a simpler interface for callers that just need the response text.
        Replaces the deprecated approval_handler.run_provider().

        Args:
            provider_key: Registered provider key
            prompt: The prompt text to send
            system_prompt: Optional system prompt

        Returns:
            Response string, or None if awaiting response

        Raises:
            ProviderError: If provider fails
            KeyError: If provider_key is not registered
        """
        result = self.execute(provider_key, prompt, system_prompt=system_prompt)

        if result.awaiting_response:
            return None

        return result.response
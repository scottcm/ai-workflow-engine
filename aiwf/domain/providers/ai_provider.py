from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiwf.domain.models.ai_provider_result import AIProviderResult


class AIProvider(ABC):
    """Abstract interface for AI providers (Strategy pattern).

    AI providers generate responses to prompts. They may call AI APIs
    (Claude, Gemini) or signal manual mode where the user provides the response.

    This is distinct from:
    - ApprovalProvider: decides whether to approve/reject content
    - StandardsProvider: creates standards bundles

    Providers with fs_ability="local-write" can write files directly.
    Providers with fs_ability="none" return file content for engine to write.
    """

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with keys: name, description, requires_config, config_keys,
                           default_connection_timeout, default_response_timeout,
                           fs_ability, supports_system_prompt, supports_file_attachments
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,  # seconds
            "default_response_timeout": 300,  # 5 minutes
            # Capability fields
            "fs_ability": "local-write",  # Default: assume best case
            "supports_system_prompt": False,
            "supports_file_attachments": False,
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
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> "AIProviderResult | None":
        """Generate response for the given prompt.

        Args:
            prompt: The prompt text to send
            context: Optional context dictionary with:
                - session_dir: Path to session directory
                - project_root: Path to project root
                - expected_outputs: List of expected output files
            system_prompt: Optional system prompt for providers that support it
            connection_timeout: Timeout for establishing connection (None = use default)
            response_timeout: Timeout for receiving response (None = use default)

        Returns:
            AIProviderResult with files dict, or None for ManualAIProvider.
            For local-write providers: files dict values are None (already written).
            For API providers: files dict values are content strings.

        Raises:
            ProviderError: If the provider call fails (network, auth, timeout, etc.)
        """
        ...
# AI providers (ADR-0016)
from .ai_provider import AIProvider
from .provider_factory import AIProviderFactory
from .manual_provider import ManualAIProvider
from .claude_code_provider import ClaudeCodeAIProvider
from .gemini_cli_provider import GeminiCliAIProvider

# Approval providers (ADR-0015)
from .approval_provider import (
    ApprovalProvider,
    SkipApprovalProvider,
    ManualApprovalProvider,
)
from .ai_approval_provider import AIApprovalProvider
from .approval_factory import ApprovalProviderFactory

# Register built-in providers (keys unchanged per ADR-0016)
AIProviderFactory.register("manual", ManualAIProvider)
AIProviderFactory.register("claude-code", ClaudeCodeAIProvider)
AIProviderFactory.register("gemini-cli", GeminiCliAIProvider)

__all__ = [
    # AI providers
    "AIProvider",
    "AIProviderFactory",
    "ManualAIProvider",
    "ClaudeCodeAIProvider",
    "GeminiCliAIProvider",
    # Approval providers
    "ApprovalProvider",
    "SkipApprovalProvider",
    "ManualApprovalProvider",
    "AIApprovalProvider",
    "ApprovalProviderFactory",
]

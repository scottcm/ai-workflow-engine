from .response_provider import ResponseProvider, AIProvider  # AIProvider is backwards compat alias
from .provider_factory import ResponseProviderFactory
from .manual_provider import ManualProvider
from .claude_code_provider import ClaudeCodeProvider

# Backwards compatibility alias
ProviderFactory = ResponseProviderFactory

# Register built-in providers
ResponseProviderFactory.register("manual", ManualProvider)
ResponseProviderFactory.register("claude-code", ClaudeCodeProvider)

__all__ = [
    "ResponseProvider",
    "AIProvider",
    "ResponseProviderFactory",
    "ProviderFactory",
    "ManualProvider",
    "ClaudeCodeProvider",
]

"""Domain-level exceptions for the AI Workflow Engine."""


class ProviderError(Exception):
    """Raised when a provider fails (network, auth, timeout, etc.)."""

    pass
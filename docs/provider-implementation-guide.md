# Response Provider Implementation Guide

This guide explains how to implement a custom response provider for the AI Workflow Engine.

## Overview

Response providers enable automated workflow execution by calling external AI services (LLMs). The engine invokes providers during the `approve` command for ING phases (PLANNING, GENERATING, REVIEWING, REVISING).

**Key behaviors:**
- `validate()` is called during `initialize_run()` to fail fast before workflow starts
- `generate()` returns a response string, or `None` for manual mode (user provides response)
- `ProviderError` propagates to the orchestrator which sets ERROR status and emits WORKFLOW_FAILED event
- Timeouts come from provider metadata (per-call overrides are out of scope per ADR-0007)

## The ResponseProvider Interface

```python
from abc import ABC, abstractmethod
from typing import Any


class ResponseProvider(ABC):
    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata.

        Keys:
        - name: Provider identifier
        - description: Human-readable description
        - requires_config: Whether provider needs configuration
        - config_keys: List of required config keys (e.g., ["api_key"])
        - default_connection_timeout: Seconds to wait for connection (default: 10)
        - default_response_timeout: Seconds to wait for response (default: 300)
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
        }

    @abstractmethod
    def validate(self) -> None:
        """Verify provider is accessible and configured correctly.

        Called at workflow init time to fail fast.
        Raises ProviderError if misconfigured or unreachable.
        """
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        """Generate AI response.

        Args:
            prompt: The prompt string to send to the AI
            context: Optional context dict (reserved for future use)
            connection_timeout: Seconds to wait for connection
            response_timeout: Seconds to wait for response

        Returns:
            Response string from the AI, or None for manual mode.
        """
        ...
```

## Implementation Example

Here's a complete example of a custom provider:

```python
from typing import Any

from aiwf.domain.providers.response_provider import ResponseProvider
from aiwf.domain.errors import ProviderError


class MyProvider(ResponseProvider):
    """Custom provider that calls an external AI API."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._api_key = self.config.get("api_key")

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "my-provider",
            "description": "My custom AI provider",
            "requires_config": True,
            "config_keys": ["api_key"],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
        }

    def validate(self) -> None:
        """Check that API key is configured and valid."""
        if not self._api_key:
            raise ProviderError("API key not configured for my-provider")

        # Optionally verify connectivity
        # try:
        #     self._client.ping()
        # except ConnectionError as e:
        #     raise ProviderError(f"Cannot connect to API: {e}")

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Call the external API and return the response."""
        # Your API call here
        response = self._call_api(
            prompt=prompt,
            timeout=(connection_timeout, response_timeout),
        )
        return response.text
```

## Registration

Register your provider with the factory so it can be referenced by key:

```python
from aiwf.domain.providers.provider_factory import ProviderFactory
from my_module import MyProvider

ProviderFactory.register("my-provider", MyProvider)
```

Users can then specify `--provider planner=my-provider` when initializing a workflow.

## Error Handling

Providers should raise `ProviderError` for any failure conditions:

```python
from aiwf.domain.errors import ProviderError

# In validate():
raise ProviderError("API key not configured")

# In generate():
raise ProviderError(f"API request failed: {response.status_code}")
raise ProviderError(f"Connection timeout after {connection_timeout}s")
```

The orchestrator catches `ProviderError` in its `approve()` method and:
1. Sets workflow status to ERROR
2. Records the error message in `state.last_error`
3. Emits a WORKFLOW_FAILED event

## Testing

For unit tests, use `FakeProvider` from `tests/conftest.py` or create test-specific providers:

```python
class FailingProvider(ResponseProvider):
    """Provider that always fails validation."""

    def validate(self) -> None:
        raise ProviderError("Intentional failure for testing")

    def generate(self, prompt, context=None, connection_timeout=None, response_timeout=None):
        return None
```

Register test providers in a fixture with cleanup:

```python
@pytest.fixture
def register_test_provider():
    ProviderFactory.register("failing", FailingProvider)
    yield
    del ProviderFactory._registry["failing"]
```

## See Also

- [ADR-0007: Plugin Architecture](adr/0007-plugin-architecture.md) - Design rationale for the provider system
- [aiwf/domain/providers/manual_provider.py](../aiwf/domain/providers/manual_provider.py) - Reference implementation for manual mode
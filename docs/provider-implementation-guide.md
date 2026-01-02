# Response Provider Implementation Guide

This guide explains how to implement a custom response provider for the AI Workflow Engine.

## Overview

Response providers enable automated workflow execution by calling external AI services (LLMs). The engine invokes providers during the `approve` command for ING phases (PLANNING, GENERATING, REVIEWING, REVISING).

**Key behaviors:**
- `validate()` is called during `initialize_run()` to fail fast before workflow starts
- `generate()` returns a `ProviderResult`, or `None` for manual mode (user provides response)
- `ProviderError` propagates to the orchestrator which sets ERROR status and emits WORKFLOW_FAILED event
- Timeouts come from provider metadata (per-call overrides are out of scope per ADR-0007)

## Provider Capabilities (fs_ability)

Providers declare their file system access level via `fs_ability` metadata:

| fs_ability | Can Read | Can Write | Examples |
|------------|----------|-----------|----------|
| `local-write` | Yes | Yes | Claude Code, Aider |
| `local-read` | Yes | No | Standards providers |
| `none` | No | No | API-only (Claude API, OpenAI) |

**Local-write providers** write code files directly. The engine validates files exist after execution.

**Non-writing providers** return file content in `ProviderResult.files`. The engine writes files.

## The ProviderResult Model

Providers return a `ProviderResult` that supports both file-writing and content-returning modes:

```python
from pydantic import BaseModel


class ProviderResult(BaseModel):
    """Result from AI provider execution."""

    files: dict[str, str | None]  # {path: content or None if already written}
    response: str | None = None   # Optional commentary for response file
```

**File handling:**
- `files` dict keys are paths relative to `/code` directory
- Value is file content (string) or `None` if provider wrote the file directly
- Engine writes files where content is provided, validates existence where `None`
- Engine warns (does not fail) if expected files are missing

| Provider Type | `files` Values | Engine Action |
|---------------|----------------|---------------|
| Local-write (Claude Code, Aider) | `None` for all | Validate files exist |
| Non-writing (web chat, API-only) | Content strings | Write files to `/code` |
| Mixed | Some `None`, some content | Write where needed, validate rest |

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
        - fs_ability: File access level ("local-write", "local-read", "none")
        - supports_system_prompt: Whether provider can use system prompts
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
            "fs_ability": "local-write",
            "supports_system_prompt": False,
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
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> ProviderResult | None:
        """Generate AI response.

        Args:
            prompt: The prompt string to send to the AI
            context: Context dict with session_dir, project_root, etc.
            system_prompt: Optional system prompt (if provider supports it)
            connection_timeout: Seconds to wait for connection
            response_timeout: Seconds to wait for response

        Returns:
            ProviderResult with files dict, or None for manual mode.
        """
        ...
```

## Implementation Examples

### API Provider (Non-Writing)

Returns file content for engine to write:

```python
from typing import Any

from aiwf.domain.providers.response_provider import ResponseProvider
from aiwf.domain.models.provider_result import ProviderResult
from aiwf.domain.errors import ProviderError


class MyApiProvider(ResponseProvider):
    """API-based provider - returns content, engine writes files."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._api_key = self.config.get("api_key")

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "my-api",
            "description": "My API provider",
            "requires_config": True,
            "config_keys": ["api_key"],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
            "fs_ability": "none",  # API-only, no file access
            "supports_system_prompt": True,
        }

    def validate(self) -> None:
        if not self._api_key:
            raise ProviderError("API key not configured")

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> ProviderResult:
        """Call API and return content for engine to write."""
        response = self._call_api(prompt, system_prompt)

        # Parse response to extract files
        files = self._parse_code_blocks(response.text)

        # Return content - engine will write files
        return ProviderResult(
            files=files,  # {"Entity.java": "package com...", ...}
            response=response.text,  # Optional: full response for logging
        )
```

### Local-Write Provider (Claude Code, Aider)

Writes files directly, returns `None` values:

```python
class ClaudeCodeProvider(ResponseProvider):
    """Local-write provider - writes files directly."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "claude-code",
            "description": "Claude Code CLI agent",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 30,
            "default_response_timeout": 600,
            "fs_ability": "local-write",  # Can write files directly
            "supports_system_prompt": True,
        }

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> ProviderResult:
        """Invoke CLI - it writes files directly."""
        # Prompt tells Claude what files to create and where
        self._invoke_claude_cli(prompt, context)

        # Return None values - engine validates files exist
        expected_files = context.get("expected_outputs", [])
        return ProviderResult(
            files={f: None for f in expected_files},  # None = already written
            response=None,  # Response file also written by Claude
        )
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
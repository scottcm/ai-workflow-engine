# Claude Code Provider Specification

**Status:** COMPLETE
**ADR:** [ADR-0013](../adr/0013-claude-code-provider.md)
**Last Updated:** January 2, 2026

---

## Overview

The `ClaudeCodeProvider` uses the Claude Agent SDK (`claude-agent-sdk`) instead of CLI subprocess. This eliminates platform-specific code and aligns with Anthropic's recommended approach for production automation.

---

## Interface

**File:** `aiwf/domain/providers/claude_code_provider.py`

```python
class ClaudeCodeProvider(ResponseProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None: ...
    def validate(self) -> None: ...
    def generate(self, prompt: str, context: dict[str, Any] | None = None, ...) -> ProviderResult: ...
    @classmethod
    def get_metadata(cls) -> dict[str, Any]: ...
```

**Internal methods:**
```python
async def _async_generate(self, prompt: str, context: dict[str, Any] | None) -> ProviderResult: ...
def _build_options(self, context: dict[str, Any] | None) -> ClaudeAgentOptions: ...
def _extract_files_written(self, messages: list) -> dict[str, None]: ...
```

---

## Configuration Mapping

| Config Key | SDK Mapping | Type |
|------------|-------------|------|
| `model` | `ClaudeAgentOptions.model` | Direct parameter |
| `allowed_tools` | `ClaudeAgentOptions.allowed_tools` | Direct parameter |
| `permission_mode` | `ClaudeAgentOptions.permission_mode` | Direct parameter |
| `working_dir` | `ClaudeAgentOptions.cwd` | Direct parameter |
| `max_turns` | `ClaudeAgentOptions.max_turns` | Direct parameter |
| `add_dirs` | `ClaudeAgentOptions.add_dirs` | Direct parameter |
| `max_output_tokens` | `env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"]` | Environment variable |
| `max_thinking_tokens` | `env["MAX_THINKING_TOKENS"]` | Environment variable |
| `max_budget_usd` | `extra_args["--max-budget-usd"]` | CLI flag |

---

## Async Wrapper Pattern

```python
import asyncio

def generate(self, prompt: str, context: dict[str, Any] | None = None, **kwargs) -> ProviderResult:
    """Sync wrapper for async SDK."""
    return asyncio.run(self._async_generate(prompt, context))

async def _async_generate(self, prompt: str, context: dict[str, Any] | None) -> ProviderResult:
    """Async implementation using SDK."""
    options = self._build_options(context)

    response_text = ""
    files_written: dict[str, None] = {}

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            # Collect text response
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text
                # Track file writes
                if isinstance(block, ToolUseBlock) and block.name == "Write":
                    file_path = block.input.get("file_path")
                    if file_path:
                        files_written[file_path] = None

    return ProviderResult(response=response_text, files=files_written)
```

---

## Error Handling

| SDK Exception | Wrapped As |
|---------------|------------|
| `ImportError` (SDK not installed) | `ProviderError` with install instructions |
| `CLINotFoundError` | `ProviderError` with CLI install instructions |
| `ProcessError` | `ProviderError` with stderr if available |
| `CLIJSONDecodeError` | `ProviderError` with parse error details |
| `TimeoutError` | `ProviderError` suggesting config increase |

```python
def validate(self) -> None:
    """Verify SDK and CLI are available."""
    try:
        from claude_agent_sdk import query
    except ImportError:
        raise ProviderError(
            "claude-agent-sdk not installed. "
            "Install with: pip install claude-agent-sdk"
        )

    if shutil.which("claude") is None:
        raise ProviderError(
            "Claude Code CLI not found. "
            "Install from: https://docs.anthropic.com/claude-code"
        )
```

---

## Metadata

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "claude-code",
        "description": "Claude Code AI agent via Agent SDK",
        "requires_config": False,
        "config_keys": [
            "model",
            "allowed_tools",
            "permission_mode",
            "max_output_tokens",
            "max_budget_usd",
            "max_thinking_tokens",
            "working_dir",
            "max_turns",
            "add_dirs",
        ],
        "default_response_timeout": 600,
        "fs_ability": "local-write",
    }
```

---

## Test Organization

```
tests/
  unit/
    domain/providers/
      test_claude_code_provider.py    # Mock SDK tests
  integration/
    test_claude_code_integration.py   # Real SDK tests (skip when CLI not installed)
```

**pytest marker:** `claude_code` - skip with `-m "not claude_code"`

---

## Key Behaviors

1. **SDK-based provider** - No subprocess, no platform-specific code
2. **Async wrapper** - `asyncio.run()` wraps async SDK in sync `generate()`
3. **File write tracking** - Parses `ToolUseBlock` with `name == "Write"`
4. **Config validation** - Warns on unknown keys, raises on invalid values
5. **Granular error handling** - Specific messages for known SDK exceptions

---

## Related Documents

- [ADR-0013: Claude Code Response Provider](../adr/0013-claude-code-provider.md)
- [Provider Implementation Guide](../provider-implementation-guide.md)
- [ADR-0007: Plugin Architecture](../adr/0007-plugin-architecture.md)

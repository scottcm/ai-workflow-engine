# Gemini CLI Provider Specification

**Status:** COMPLETE
**ADR:** [ADR-0014](../adr/0014-gemini-cli-provider.md)
**Last Updated:** January 2, 2026

---

## Overview

The `GeminiCliProvider` uses subprocess with JSON streaming output. This follows the pattern established by `ClaudeCodeProvider` but uses subprocess since no Gemini CLI SDK exists.

**Key approach:** Parse NDJSON stream from `gemini -o stream-json` to track responses and file writes.

**Prompt delivery:** File-based prompts are the norm (engine writes prompt files, provider passes file path to CLI). Direct string prompts supported via stdin for flexibility.

---

## Interface

**File:** `aiwf/domain/providers/gemini_cli_provider.py`

```python
class GeminiCliProvider(ResponseProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None: ...
    def validate(self) -> None: ...
    def generate(self, prompt: str, context: dict[str, Any] | None = None, ...) -> ProviderResult: ...
    @classmethod
    def get_metadata(cls) -> dict[str, Any]: ...
```

**Internal methods:**
```python
async def _async_generate(self, prompt: str, context: dict[str, Any] | None, system_prompt: str | None) -> ProviderResult: ...
def _build_args(self, context: dict[str, Any] | None) -> list[str]: ...
def _parse_ndjson_stream(self, stdout: bytes) -> tuple[str, dict[str, None]]: ...
def _wrap_process_error(self, returncode: int, stderr: str) -> ProviderError: ...
def _validate_config(self) -> None: ...
```

---

## Configuration Mapping

| Config Key | CLI Flag/Usage | Notes |
|------------|----------------|-------|
| `model` | `-m, --model` | Model selection |
| `sandbox` | `-s, --sandbox` | Enable sandbox mode |
| `approval_mode` | `--approval-mode` | default, auto_edit, yolo (validated enum) |
| `include_directories` | `--include-directories` | Additional workspace dirs (validated list) |
| `allowed_tools` | `--allowed-tools` | Tools without confirmation (validated list) |
| `working_dir` | `cwd` parameter | Subprocess working directory |
| `timeout` | `asyncio.wait_for()` | Process timeout in seconds |

---

## Prompt Delivery

**File-based prompts (preferred):** When `context["prompt_file"]` is provided, the provider tells Gemini to read the file via `-p "Process the prompt in <file>"`. This:
- Avoids stdin buffering issues with large prompts
- Matches the workflow engine's file-based architecture
- Lets Gemini CLI handle file reading natively

**Direct string prompts (fallback):** When no `prompt_file` is in context, the prompt string is sent via stdin for:
- Testing without writing temp files
- Ad-hoc invocations outside the normal workflow

---

## NDJSON Event Types

| Event Type | Fields | Action |
|------------|--------|--------|
| `init` | `session_id`, `model` | Log session info |
| `message` | `role`, `content`, `delta` | Collect assistant text |
| `tool_use` | `tool_name`, `tool_id`, `parameters` | Track pending file writes |
| `tool_result` | `tool_id`, `status` | Confirm successful writes |
| `result` | `status`, `stats` | Log final status |

---

## File Write Tools

Track both tools that modify files:

| Tool Name | Purpose | Parameters |
|-----------|---------|------------|
| `write_file` | Create new files | `file_path`, `content` |
| `replace` | Edit existing files | `file_path`, `old_string`, `new_string` |

---

## Error Handling

```python
def _wrap_process_error(self, returncode: int, stderr: str) -> ProviderError:
    """Wrap subprocess errors with actionable messages."""
    stderr_lower = stderr.lower()

    if "auth" in stderr_lower or "login" in stderr_lower:
        return ProviderError(
            f"Gemini CLI authentication error. Run: gemini auth login\n{stderr}"
        )
    elif returncode == 127:
        return ProviderError(
            "Gemini CLI not found. "
            "Install from: https://github.com/google-gemini/gemini-cli"
        )
    else:
        return ProviderError(
            f"Gemini CLI failed (exit {returncode}): {stderr}"
        )
```

---

## Metadata

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "gemini-cli",
        "description": "Gemini CLI AI agent via subprocess",
        "requires_config": False,
        "config_keys": [
            "model",
            "sandbox",
            "approval_mode",
            "include_directories",
            "allowed_tools",
            "working_dir",
            "timeout",
        ],
        "default_response_timeout": 600,
        "fs_ability": "local-write",
    }
```

---

## Config Validation

```python
def _validate_config(self) -> None:
    """Validate configuration and warn on unknown keys."""
    # Validate timeout
    timeout = self.config.get("timeout")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be > 0")

    # Validate approval_mode enum
    approval_mode = self.config.get("approval_mode")
    valid_modes = {"default", "auto_edit", "yolo"}
    if approval_mode is not None and approval_mode not in valid_modes:
        raise ValueError(
            f"approval_mode must be one of {sorted(valid_modes)}, got: {approval_mode!r}"
        )

    # Validate list types
    for key in ("include_directories", "allowed_tools"):
        value = self.config.get(key)
        if value is not None and not isinstance(value, list):
            raise ValueError(f"{key} must be a list, got: {type(value).__name__}")
```

---

## Test Organization

```
tests/
  unit/
    domain/providers/
      test_gemini_cli_provider.py    # Mock subprocess tests (52 tests)
  integration/
    test_gemini_cli_integration.py   # Real CLI tests (skip when not installed)
```

**pytest marker:** `gemini_cli` - skip with `-m "not gemini_cli"`

---

## Key Behaviors

1. **Subprocess-based** - Uses async subprocess with NDJSON parsing
2. **File-based prompts preferred** - Avoids stdin buffering issues
3. **Tracks both write tools** - `write_file` and `replace`
4. **Success verification** - Only tracks files with `tool_result.status == "success"`
5. **Per-line error recovery** - Malformed JSON logged with content sample
6. **Windows compatibility** - Uses `shutil.which()` for full path resolution

---

## Differences from Claude Code Provider

| Aspect | Claude Code | Gemini CLI |
|--------|-------------|------------|
| Integration | SDK (`claude-agent-sdk`) | Subprocess |
| Prompt delivery | SDK handles | File-based (preferred) or stdin |
| Output parsing | SDK typed objects | NDJSON line parsing |
| File tracking | `ToolUseBlock.name == "Write"` | `tool_name in {"write_file", "replace"}` |
| Success check | Implicit (SDK) | Explicit (`tool_result.status`) |
| Error handling | SDK exceptions | Subprocess exit codes + stderr |
| Cost controls | `--max-budget-usd` | Not available (use timeout) |
| Config validation | SDK validates | Manual enum/list validation |

---

## Related Documents

- [ADR-0014: Gemini CLI Response Provider](../adr/0014-gemini-cli-provider.md)
- [ADR-0013: Claude Code Response Provider](../adr/0013-claude-code-provider.md)
- [Provider Implementation Guide](../provider-implementation-guide.md)

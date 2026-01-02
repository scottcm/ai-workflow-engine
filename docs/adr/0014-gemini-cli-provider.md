# ADR-0014: Gemini CLI Response Provider

**Status:** Draft
**Date:** January 2, 2025
**Deciders:** Scott

---

## Context and Problem Statement

With the Claude Code provider (ADR-0013) complete, users have requested support for additional AI agents. Google's Gemini CLI is a comparable tool with local filesystem access that could serve as an alternative provider.

Unlike Claude Code, there is no official Python SDK for Gemini CLI. However, the CLI supports JSON streaming output (`--output-format stream-json`) that reports tool calls including file writes, making subprocess integration viable.

**Goal:** Implement a Gemini CLI provider that offers similar functionality to the Claude Code provider, providing users with choice between AI backends.

---

## Decision Drivers

1. **Parity with Claude Code** - Similar capabilities and configuration options
2. **Windows Support** - Must work on Windows without WSL (confirmed working)
3. **File Write Tracking** - Must track files written for engine validation
4. **Cost Control** - Users should be able to limit token usage
5. **Minimal Dependencies** - No external SDK required (subprocess-based)

---

## Considered Options

### Option 1: Gemini CLI Subprocess with Stream JSON

Invoke Gemini CLI via `subprocess.Popen()` with `--output-format stream-json`.

**Pros:**
- No Python SDK dependency
- JSON streaming provides structured tool call events
- File write tracking via `tool_use` events
- Windows native support (confirmed)
- YOLO mode (`-y`) for auto-approval

**Cons:**
- Subprocess management complexity
- Must parse NDJSON stream
- No typed message objects

### Option 2: Gemini API SDK (google-genai)

Use the `google-genai` Python package for direct API access.

**Pros:**
- Native Python SDK
- Structured output support

**Cons:**
- Requires API key (different auth model than CLI OAuth)
- No built-in file tools - must implement Read/Write/Edit ourselves
- Must implement sandboxing/security ourselves
- Significantly more work

### Option 3: Wait for Official SDK

Wait for Google to release a CLI wrapper SDK similar to `claude-agent-sdk`.

**Pros:**
- Would simplify implementation
- Typed interfaces

**Cons:**
- No indication this is planned
- Delays provider availability indefinitely

---

## Decision Outcome

**Chosen option: Option 1 (Gemini CLI Subprocess with Stream JSON)**

The CLI provides excellent JSON streaming output that reports all tool calls including file writes. This approach:
- Works on Windows natively (tested)
- Requires no additional Python dependencies
- Provides all information needed for file tracking

---

## Design Decisions

### JSON Output Format

Gemini CLI supports three output formats:
- `text` - Human readable (default)
- `json` - Final summary JSON
- `stream-json` - **NDJSON events during execution** (chosen)

The `stream-json` format emits events as newline-delimited JSON:

```json
{"type":"init","session_id":"...","model":"auto-gemini-3"}
{"type":"message","role":"user","content":"..."}
{"type":"message","role":"assistant","content":"...","delta":true}
{"type":"tool_use","tool_name":"write_file","parameters":{"file_path":"test.txt","content":"..."}}
{"type":"tool_result","tool_id":"...","status":"success"}
{"type":"result","status":"success","stats":{...}}
```

**Rationale:** Stream JSON provides real-time tool call events, enabling accurate file write tracking without post-execution file system diffing.

---

### File Write Tracking

Track file modifications by parsing `tool_use` and `tool_result` events. Gemini CLI uses two tools for file modifications:

| Tool Name | Purpose |
|-----------|---------|
| `write_file` | Create new files |
| `replace` | Edit existing files (search/replace) |

**Important:** Only track files where `tool_result.status == "success"` to avoid tracking failed writes.

```python
FILE_WRITE_TOOLS = {"write_file", "replace"}

pending_writes: dict[str, str] = {}  # tool_id -> file_path
files_written: dict[str, None] = {}

for line in process.stdout:
    event = json.loads(line)

    # Track tool invocations
    if event["type"] == "tool_use" and event["tool_name"] in FILE_WRITE_TOOLS:
        tool_id = event["tool_id"]
        file_path = event["parameters"]["file_path"]
        pending_writes[tool_id] = file_path

    # Confirm successful writes
    if event["type"] == "tool_result" and event.get("status") == "success":
        tool_id = event["tool_id"]
        if tool_id in pending_writes:
            files_written[pending_writes[tool_id]] = None
```

Return `{file_path: None}` per ADR-0011 convention (provider wrote directly).

---

### Auto-Approval Mode

Use YOLO mode (`-y` or `--yolo`) for unattended execution:

```bash
gemini -o stream-json -y "prompt here"
```

Alternative: `--approval-mode yolo` for explicit configuration.

**Rationale:** Matches Claude Code's `acceptEdits` permission mode behavior.

---

### Authentication

Gemini CLI uses OAuth authentication via `gemini auth login`. No API key required.

**Rationale:** Same pattern as Claude Code - users authenticate once via CLI.

---

### Configuration Options

| Config Key | CLI Flag | Purpose |
|------------|----------|---------|
| `model` | `-m, --model` | Model selection |
| `sandbox` | `-s, --sandbox` | Enable sandbox mode |
| `approval_mode` | `--approval-mode` | Approval mode (default, auto_edit, yolo) |
| `include_directories` | `--include-directories` | Additional workspace directories |
| `allowed_tools` | `--allowed-tools` | Tools allowed without confirmation |
| `working_dir` | (cwd parameter) | Working directory for CLI |
| `timeout` | (asyncio.wait_for) | Process timeout in seconds (default: 600) |

**Limitations:** Gemini CLI does not have direct equivalents for:
- `max_budget_usd` - No cost limit flag (use `timeout` as guard)
- `max_turns` - No iteration limit flag
- `max_output_tokens` - No token limit flag

---

### Process Management

Use `asyncio.create_subprocess_exec()` for async subprocess management. Pass prompt via stdin to avoid shell quoting issues and support large prompts:

```python
async def _async_generate(self, prompt: str, ...) -> ProviderResult:
    process = await asyncio.create_subprocess_exec(
        "gemini",
        "-o", "stream-json",
        "-y",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
    )

    # Send prompt via stdin
    stdout_data, stderr_data = await process.communicate(input=prompt.encode())

    pending_writes: dict[str, str] = {}
    files_written: dict[str, None] = {}
    response_text = ""
    parse_errors: list[str] = []

    for line in stdout_data.decode().splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            parse_errors.append(f"Line {len(parse_errors)+1}: {str(e)[:50]}")
            continue

        if event["type"] == "message" and event.get("role") == "assistant":
            response_text += event.get("content", "")
        elif event["type"] == "tool_use" and event["tool_name"] in FILE_WRITE_TOOLS:
            pending_writes[event["tool_id"]] = event["parameters"]["file_path"]
        elif event["type"] == "tool_result" and event.get("status") == "success":
            if event["tool_id"] in pending_writes:
                files_written[pending_writes[event["tool_id"]]] = None

    # Log stderr even on success (may contain warnings)
    if stderr_data:
        logger.debug(f"Gemini CLI stderr: {stderr_data.decode()}")

    if parse_errors:
        logger.warning(f"Malformed JSON lines: {parse_errors}")

    return ProviderResult(response=response_text, files=files_written)
```

**Rationale:**
- Stdin avoids shell quoting issues and argument length limits
- Per-line JSON parsing with error recovery handles malformed output
- Stderr captured for debugging even on success

---

### Sync Wrapper

Same pattern as Claude Code provider - wrap async with `asyncio.run()`:

```python
def generate(self, prompt: str, ...) -> ProviderResult:
    return asyncio.run(self._async_generate(prompt, context, system_prompt))
```

---

## Provider Interface

```python
class GeminiCliProvider(ResponseProvider):
    """Gemini CLI response provider using subprocess."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize with optional configuration."""

    def validate(self) -> None:
        """Verify Gemini CLI is available."""

    def generate(self, prompt: str, context: dict[str, Any] | None = None) -> ProviderResult:
        """Generate response using Gemini CLI subprocess."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata."""
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

## Error Handling

| Condition | Handling |
|-----------|----------|
| CLI not found | `shutil.which("gemini")` returns None, raise `ProviderError` with install URL |
| Process error | Non-zero exit code, wrap stderr as `ProviderError` |
| JSON parse error | Log warning, continue processing remaining lines (non-fatal) |
| Auth error | CLI stderr contains "auth", suggest `gemini auth login` |
| Timeout | Process timeout via `asyncio.wait_for()`, raise `ProviderError` |
| Empty response | Return empty string (profile handles validation) |

**Error wrapping pattern** (matches Claude Code provider):

```python
def _wrap_process_error(self, returncode: int, stderr: str) -> ProviderError:
    """Wrap subprocess errors with actionable messages."""
    if "auth" in stderr.lower() or "login" in stderr.lower():
        return ProviderError(
            f"Gemini CLI authentication error. Run: gemini auth login\n{stderr}"
        )
    elif returncode == 127:  # Command not found
        return ProviderError(
            "Gemini CLI not found. Install with: npm i -g @anthropic/gemini-cli"
        )
    else:
        return ProviderError(f"Gemini CLI failed (exit {returncode}): {stderr}")
```

---

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Windows | **Confirmed** | Native support, tested with stream-json |
| macOS | Expected | Standard CLI behavior |
| Linux | Expected | Standard CLI behavior |

**Windows verification:**
```bash
$ gemini -o stream-json "What is 2+2?"
{"type":"init","session_id":"...","model":"auto-gemini-3"}
{"type":"message","role":"assistant","content":"4","delta":true}
{"type":"result","status":"success",...}
```

---

## Dependencies

| Dependency | Type | Description |
|------------|------|-------------|
| Gemini CLI | Runtime | Must be installed (`npm i -g @anthropic/gemini-cli` or via installer) |
| ADR-0007 | Architecture | Provider plugin infrastructure |
| ADR-0013 | Reference | Similar implementation pattern |

**Note:** Verify correct npm package name before implementation. The CLI may be distributed via a different channel.

---

## Implementation Plan

| Task | Priority | Notes |
|------|----------|-------|
| Implement `GeminiCliProvider` with subprocess | High | Stream JSON parsing via stdin |
| Add validation (CLI availability check) | High | `shutil.which()` |
| Handle NDJSON parsing with error recovery | High | Try/catch per line, log warnings |
| Track `write_file` AND `replace` tool calls | High | Both tools modify files |
| Verify success via `tool_result.status` | High | Only track successful writes |
| Capture stderr for debugging | Medium | Log even on success |
| Create unit tests | High | Mock subprocess |
| Register provider in factory | Medium | ResponseProviderFactory |
| Create integration tests | Medium | Real CLI invocation |
| Add pytest marker | Low | `gemini_cli` marker |

**Test Coverage (per review):**
- Mixed `message`/`tool_use` events
- Multiple `write_file` calls
- Multiple `replace` calls
- Failed tool calls (not tracked)
- Malformed JSON lines (warning, continue)
- Process timeout
- Auth errors

---

## Comparison with Claude Code Provider

| Aspect | Claude Code | Gemini CLI |
|--------|-------------|------------|
| Integration | SDK (`claude-agent-sdk`) | Subprocess |
| JSON output | SDK streaming | `--output-format stream-json` |
| File tracking | `ToolUseBlock` (Write) | `tool_use` events (write_file, replace) |
| Success verification | Implicit (SDK) | Explicit (`tool_result.status`) |
| Auto-approval | `acceptEdits` mode | `-y` (YOLO mode) |
| Windows | Full support | Full support |
| Cost control | `--max-budget-usd` | Not available (use timeout) |
| Token limits | `max_output_tokens` env | Not available |

---

## Resolved Questions

1. **Edit tool tracking:** ✅ RESOLVED - Gemini CLI uses `replace` (not `edit_file`) for editing existing files. Implementation tracks both `write_file` and `replace` tools.

## Open Questions

1. **Cost/token limits:** Gemini CLI doesn't expose budget or token limit flags.
   - **Decision:** Accept limitation, document clearly, use timeout as only guard
   - Consider requesting feature from Google if users need it

---

## Related Decisions

- **ADR-0007:** Plugin architecture (provider infrastructure)
- **ADR-0013:** Claude Code provider (similar pattern, reference implementation)

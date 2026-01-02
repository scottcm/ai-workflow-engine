# ADR-0014: Gemini CLI Provider Implementation Plan

**Status:** NOT STARTED
**ADR:** [ADR-0014](../adr/0014-gemini-cli-provider.md)
**Created:** January 2, 2025

---

## Overview

Implement `GeminiCliProvider` using subprocess with JSON streaming output. This follows the pattern established by `ClaudeCodeProvider` but uses subprocess instead of SDK since no Gemini CLI SDK exists.

**Key approach:** Parse NDJSON stream from `gemini -o stream-json` to track responses and file writes.

**Prompt delivery:** File-based prompts are the norm (engine writes prompt files, provider passes file path to CLI). Direct string prompts supported via stdin for flexibility.

---

## Progress Tracking

> **For AI agents:** Check this section first. Update status after each phase completion.

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Provider Implementation | COMPLETE | Subprocess with stream-json parsing |
| 2. Unit Tests | COMPLETE | 52 tests passing |
| 3. Integration Tests | COMPLETE | Real CLI invocation tests (skip when not installed) |
| 4. Registration | COMPLETE | Registered as "gemini-cli" |

**Current Phase:** COMPLETE
**Blocking Issues:** None

---

## Prerequisites

Before starting implementation:
- [ ] ADR-0014 reviewed and approved
- [ ] Gemini CLI installed and authenticated (`gemini auth login`)
- [ ] Claude Code provider complete (reference implementation)

---

## Test Approach

### Philosophy
- **TDD for Phase 2** - Write unit tests before fixing any bugs found
- **Test-after for Phase 1** - Implement provider, then write tests
- **Integration tests last** - Require real Gemini CLI

### Test Organization
```
tests/
  unit/
    domain/providers/
      test_gemini_cli_provider.py    # Phase 2: Mock subprocess tests
  integration/
    test_gemini_cli_integration.py   # Phase 3: Real CLI tests
```

### What to Test
- Subprocess argument building
- NDJSON parsing (all event types)
- File write tracking (`write_file` and `replace` tools)
- Success verification via `tool_result.status`
- Error handling (process errors, JSON parse errors, auth errors)
- Timeout handling
- Config validation

### What NOT to Test
- Gemini CLI internals
- Actual Gemini API responses (integration only)

---

## Phase 1: Provider Implementation

**Goal:** Implement `GeminiCliProvider` using async subprocess with NDJSON parsing.

**TDD:** No (new implementation)

### Spec

**File:** `aiwf/domain/providers/gemini_cli_provider.py`

**Interface:**
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

### Configuration Mapping

| Config Key | CLI Flag/Usage | Notes |
|------------|----------------|-------|
| `model` | `-m, --model` | Model selection |
| `sandbox` | `-s, --sandbox` | Enable sandbox mode |
| `approval_mode` | `--approval-mode` | default, auto_edit, yolo (validated enum) |
| `include_directories` | `--include-directories` | Additional workspace dirs (validated list) |
| `allowed_tools` | `--allowed-tools` | Tools without confirmation (validated list) |
| `working_dir` | `cwd` parameter | Subprocess working directory |
| `timeout` | `asyncio.wait_for()` | Process timeout in seconds |

### Prompt Delivery

**File-based prompts (preferred):** The orchestrator writes prompt files (e.g., `planning-prompt.md`). When `context["prompt_file"]` is provided, the provider passes the file path directly to Gemini CLI instead of using stdin. This:
- Avoids stdin buffering issues with large prompts
- Matches the workflow engine's file-based architecture
- Lets Gemini CLI handle file reading natively

**Direct string prompts (fallback):** When no `prompt_file` is in context, the prompt string is sent via stdin. This supports:
- Testing without writing temp files
- Ad-hoc invocations outside the normal workflow

```python
# In _async_generate():
if context and context.get("prompt_file"):
    # File-based: pass path to CLI
    args.extend(["--prompt-file", context["prompt_file"]])
    stdin_input = None
else:
    # Stdin-based: send prompt directly
    stdin_input = full_prompt.encode()
```

**Note on stdin buffering:** When using stdin for large prompts (>64KB), subprocess buffering is handled by `process.communicate()` which manages pipes correctly. However, file-based delivery is recommended for prompts exceeding 100KB to avoid potential platform-specific buffering differences.

### NDJSON Event Types

| Event Type | Fields | Action |
|------------|--------|--------|
| `init` | `session_id`, `model` | Log session info |
| `message` | `role`, `content`, `delta` | Collect assistant text |
| `tool_use` | `tool_name`, `tool_id`, `parameters` | Track pending file writes |
| `tool_result` | `tool_id`, `status` | Confirm successful writes |
| `result` | `status`, `stats` | Log final status |

### File Write Tools

Track both tools that modify files:

| Tool Name | Purpose | Parameters |
|-----------|---------|------------|
| `write_file` | Create new files | `file_path`, `content` |
| `replace` | Edit existing files | `file_path`, `old_string`, `new_string` |

### Core Implementation

```python
"""Gemini CLI response provider using subprocess."""

import asyncio
import json
import logging
import shutil
import warnings
from typing import Any

from aiwf.domain.errors import ProviderError
from aiwf.domain.models.provider_result import ProviderResult
from aiwf.domain.providers.response_provider import ResponseProvider

logger = logging.getLogger(__name__)

# Tools that modify files
FILE_WRITE_TOOLS = {"write_file", "replace"}

# Default timeout (10 minutes)
DEFAULT_TIMEOUT = 600


class GeminiCliProvider(ResponseProvider):
    """Gemini CLI response provider using subprocess.

    Uses Gemini CLI with stream-json output format for structured parsing.
    Tracks file writes via tool_use/tool_result events.

    Requirements:
        - Gemini CLI must be installed
        - User must be authenticated via `gemini auth login`

    Configuration:
        - model: Model to use
        - sandbox: Enable sandbox mode
        - approval_mode: Approval mode (default, auto_edit, yolo)
        - include_directories: Additional workspace directories
        - allowed_tools: Tools allowed without confirmation
        - working_dir: Working directory for CLI
        - timeout: Process timeout in seconds (default: 600)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._validate_config()

        self._model = self.config.get("model")
        self._sandbox = self.config.get("sandbox", False)
        self._approval_mode = self.config.get("approval_mode", "yolo")
        self._include_directories = self.config.get("include_directories", [])
        self._allowed_tools = self.config.get("allowed_tools")
        self._working_dir = self.config.get("working_dir")
        self._timeout = self.config.get("timeout", DEFAULT_TIMEOUT)

    def _validate_config(self) -> None:
        """Validate configuration and warn on unknown keys."""
        if not self.config:
            return

        known_keys = set(self.get_metadata()["config_keys"])
        unknown_keys = set(self.config.keys()) - known_keys
        if unknown_keys:
            warnings.warn(
                f"Unknown GeminiCliProvider config keys ignored: {sorted(unknown_keys)}",
                UserWarning,
                stacklevel=3,
            )

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
            "default_response_timeout": DEFAULT_TIMEOUT,
            "fs_ability": "local-write",
        }

    def validate(self) -> None:
        """Verify Gemini CLI is available."""
        if shutil.which("gemini") is None:
            raise ProviderError(
                "Gemini CLI not found. "
                "Install from: https://github.com/google-gemini/gemini-cli"
            )

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> ProviderResult:
        """Generate response using Gemini CLI subprocess."""
        return asyncio.run(self._async_generate(prompt, context, system_prompt))

    async def _async_generate(
        self,
        prompt: str,
        context: dict[str, Any] | None,
        system_prompt: str | None,
    ) -> ProviderResult:
        """Async implementation using subprocess."""
        args = self._build_args(context)

        # Resolve working directory
        cwd = self._working_dir
        if not cwd and context and context.get("project_root"):
            cwd = str(context["project_root"])

        # Determine prompt delivery method
        # File-based prompts are preferred (avoids stdin buffering, matches workflow architecture)
        prompt_file = context.get("prompt_file") if context else None
        if prompt_file:
            # File-based: pass path to CLI
            args.extend(["--prompt-file", str(prompt_file)])
            stdin_input = None
            logger.debug(f"Using file-based prompt: {prompt_file}")
        else:
            # Stdin-based: build full prompt and send via stdin
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            stdin_input = full_prompt.encode()
            logger.debug("Using stdin-based prompt")

        try:
            process = await asyncio.create_subprocess_exec(
                "gemini",
                *args,
                stdin=asyncio.subprocess.PIPE if stdin_input else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            # Send prompt (via stdin if not file-based) with timeout
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(input=stdin_input),
                timeout=self._timeout,
            )

        except asyncio.TimeoutError:
            process.kill()
            raise ProviderError(
                f"Gemini CLI timed out after {self._timeout}s. "
                "Consider increasing timeout config."
            )
        except FileNotFoundError:
            raise ProviderError(
                "Gemini CLI not found. "
                "Install from: https://github.com/google-gemini/gemini-cli"
            )

        # Log stderr even on success (may contain warnings)
        if stderr_data:
            stderr_str = stderr_data.decode()
            logger.debug(f"Gemini CLI stderr: {stderr_str}")

        # Check for process errors
        if process.returncode != 0:
            raise self._wrap_process_error(
                process.returncode,
                stderr_data.decode() if stderr_data else "",
            )

        # Parse NDJSON output
        response_text, files_written = self._parse_ndjson_stream(stdout_data)

        return ProviderResult(response=response_text, files=files_written)

    def _build_args(self, context: dict[str, Any] | None) -> list[str]:
        """Build CLI arguments from config."""
        args = ["-o", "stream-json"]

        # Approval mode (default to yolo for automation)
        if self._approval_mode == "yolo":
            args.append("-y")
        elif self._approval_mode:
            args.extend(["--approval-mode", self._approval_mode])

        if self._model:
            args.extend(["-m", self._model])

        if self._sandbox:
            args.append("-s")

        for directory in self._include_directories:
            args.extend(["--include-directories", directory])

        if self._allowed_tools:
            for tool in self._allowed_tools:
                args.extend(["--allowed-tools", tool])

        return args

    def _parse_ndjson_stream(
        self, stdout: bytes
    ) -> tuple[str, dict[str, None]]:
        """Parse NDJSON stream and extract response and file writes."""
        pending_writes: dict[str, str] = {}  # tool_id -> file_path
        files_written: dict[str, None] = {}
        response_text = ""
        parse_errors: list[str] = []

        for line in stdout.decode().splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                # Include sample of malformed content for debugging
                sample = line[:50] + "..." if len(line) > 50 else line
                parse_errors.append(f"{str(e)[:30]} | {sample!r}")
                continue

            event_type = event.get("type")

            # Collect assistant messages
            if event_type == "message" and event.get("role") == "assistant":
                content = event.get("content", "")
                if content:
                    response_text += content

            # Track file write tool invocations
            elif event_type == "tool_use":
                tool_name = event.get("tool_name")
                if tool_name in FILE_WRITE_TOOLS:
                    tool_id = event.get("tool_id")
                    file_path = event.get("parameters", {}).get("file_path")
                    if tool_id and file_path:
                        pending_writes[tool_id] = file_path

            # Confirm successful writes
            elif event_type == "tool_result":
                if event.get("status") == "success":
                    tool_id = event.get("tool_id")
                    if tool_id in pending_writes:
                        files_written[pending_writes[tool_id]] = None

        if parse_errors:
            logger.warning(f"Malformed JSON lines ({len(parse_errors)}): {parse_errors[:3]}")

        return response_text, files_written

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

### Acceptance Criteria
- [ ] Supports file-based prompts via `context["prompt_file"]` (preferred)
- [ ] Falls back to stdin for prompts without prompt_file
- [ ] Parses NDJSON stream with per-line error recovery
- [ ] Logs malformed JSON with content sample for debugging
- [ ] Tracks both `write_file` and `replace` tool calls
- [ ] Verifies success via `tool_result.status`
- [ ] Captures stderr for debugging
- [ ] Implements timeout via `asyncio.wait_for()`
- [ ] Validates config keys (warn on unknown)
- [ ] Validates `approval_mode` enum values
- [ ] Validates list types (`include_directories`, `allowed_tools`)
- [ ] All config options mapped to CLI args
- [ ] Metadata matches ADR-0014

---

## Phase 2: Unit Tests

**Goal:** Comprehensive unit tests with mocked subprocess.

**TDD:** Yes

### Spec

**File:** `tests/unit/domain/providers/test_gemini_cli_provider.py`

**Test Categories:**

#### 2.1 Initialization Tests
```python
class TestGeminiCliProviderInit:
    def test_init_with_no_config(self):
        """Provider initializes with defaults."""

    def test_init_with_full_config(self):
        """Provider accepts all config keys."""

    def test_unknown_config_keys_emit_warning(self):
        """Unknown config keys trigger UserWarning."""

    def test_invalid_timeout_raises_value_error(self):
        """timeout <= 0 raises ValueError."""

    def test_invalid_approval_mode_raises_value_error(self):
        """approval_mode not in valid set raises ValueError."""

    def test_include_directories_non_list_raises_value_error(self):
        """include_directories must be a list."""

    def test_allowed_tools_non_list_raises_value_error(self):
        """allowed_tools must be a list."""
```

#### 2.2 Validation Tests
```python
class TestGeminiCliProviderValidation:
    def test_validate_passes_when_cli_available(self):
        """validate() succeeds when CLI in PATH."""

    def test_validate_fails_when_cli_not_found(self):
        """validate() raises ProviderError with install link."""
```

#### 2.3 Argument Building Tests
```python
class TestGeminiCliProviderBuildArgs:
    def test_build_args_includes_stream_json(self):
        """Args always include -o stream-json."""

    def test_build_args_yolo_mode_adds_y_flag(self):
        """approval_mode='yolo' adds -y flag."""

    def test_build_args_maps_model(self):
        """model config maps to -m flag."""

    def test_build_args_maps_sandbox(self):
        """sandbox config maps to -s flag."""

    def test_build_args_maps_include_directories(self):
        """include_directories maps to --include-directories."""

    def test_build_args_maps_allowed_tools(self):
        """allowed_tools maps to --allowed-tools."""

    def test_build_args_with_context_project_root(self):
        """context['project_root'] used as cwd."""
```

#### 2.4 NDJSON Parsing Tests
```python
class TestGeminiCliProviderNdjsonParsing:
    def test_parse_extracts_assistant_messages(self):
        """Parser extracts text from assistant messages."""

    def test_parse_handles_multiple_messages(self):
        """Parser concatenates multiple assistant messages."""

    def test_parse_tracks_write_file_tool(self):
        """Parser tracks write_file tool calls."""

    def test_parse_tracks_replace_tool(self):
        """Parser tracks replace tool calls."""

    def test_parse_only_tracks_successful_writes(self):
        """Parser ignores failed tool_result events."""

    def test_parse_handles_malformed_json(self):
        """Parser logs warning with sample content and continues."""

    def test_parse_handles_partial_line(self):
        """Parser handles truncated/incomplete JSON lines gracefully."""

    def test_parse_handles_empty_output(self):
        """Parser returns empty response for empty output."""

    def test_parse_handles_mixed_events(self):
        """Parser handles interleaved message and tool events."""
```

#### 2.5 Generation Tests (Mocked Subprocess)
```python
class TestGeminiCliProviderGenerate:
    def test_generate_sends_prompt_via_stdin(self, mock_subprocess):
        """generate() sends prompt via subprocess stdin when no prompt_file."""

    def test_generate_uses_prompt_file_when_provided(self, mock_subprocess):
        """generate() uses --prompt-file flag when context['prompt_file'] set."""

    def test_generate_prefers_file_over_stdin(self, mock_subprocess):
        """File-based delivery is used when prompt_file is in context."""

    def test_generate_returns_response_text(self, mock_subprocess):
        """generate() returns parsed response text."""

    def test_generate_returns_files_written(self, mock_subprocess):
        """generate() returns tracked files in ProviderResult."""

    def test_generate_with_system_prompt_via_stdin(self, mock_subprocess):
        """generate() prepends system prompt when using stdin."""

    def test_generate_uses_config_timeout(self, mock_subprocess):
        """generate() uses configured timeout value."""

    def test_generate_uses_context_project_root_as_cwd(self, mock_subprocess):
        """generate() uses project_root as working directory."""
```

#### 2.6 Error Handling Tests
```python
class TestGeminiCliProviderErrorHandling:
    def test_timeout_raises_provider_error(self, mock_subprocess):
        """Timeout raises ProviderError with suggestion."""

    def test_process_error_raises_provider_error(self, mock_subprocess):
        """Non-zero exit code raises ProviderError."""

    def test_auth_error_suggests_login(self, mock_subprocess):
        """Auth errors suggest gemini auth login."""

    def test_cli_not_found_has_install_link(self, mock_subprocess):
        """FileNotFoundError includes install link."""
```

#### 2.7 Metadata Tests
```python
class TestGeminiCliProviderMetadata:
    def test_metadata_has_correct_name(self):
        """Metadata name is 'gemini-cli'."""

    def test_metadata_has_all_config_keys(self):
        """Metadata lists all supported config keys."""

    def test_metadata_fs_ability_is_local_write(self):
        """fs_ability indicates local file write capability."""
```

### Mocking Strategy

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_subprocess():
    """Mock asyncio.create_subprocess_exec."""
    with patch("asyncio.create_subprocess_exec") as mock:
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(
            b'{"type":"message","role":"assistant","content":"Hello"}\n',
            b"",
        ))
        mock.return_value = process
        yield mock, process


def make_ndjson(*events: dict) -> bytes:
    """Helper to create NDJSON byte stream."""
    lines = [json.dumps(e) for e in events]
    return "\n".join(lines).encode()
```

### Acceptance Criteria
- [ ] All test categories implemented
- [ ] Tests cover config validation (unknown keys, enum, list types)
- [ ] Tests cover file-based and stdin-based prompt delivery
- [ ] Tests verify NDJSON parsing for all event types
- [ ] Tests verify partial/malformed JSON handling with content samples
- [ ] Tests verify file tracking (write_file and replace)
- [ ] Tests verify success status checking
- [ ] Tests cover all error scenarios
- [ ] Tests use mocked subprocess (no real CLI calls)
- [ ] All tests pass

---

## Phase 3: Integration Tests

**Goal:** Test real CLI invocation with Gemini CLI.

**TDD:** No

### Spec

**File:** `tests/integration/test_gemini_cli_integration.py`

**Skip condition:** Tests skip if Gemini CLI not installed.

```python
import shutil
import pytest

GEMINI_AVAILABLE = shutil.which("gemini") is not None

@pytest.mark.skipif(not GEMINI_AVAILABLE, reason="Gemini CLI not installed")
@pytest.mark.gemini_cli
class TestGeminiCliIntegration:
    ...
```

### Test Cases

```python
def test_simple_prompt_returns_response(self):
    """Basic prompt gets a response."""
    provider = GeminiCliProvider()
    provider.validate()
    result = provider.generate("Say 'hello' and nothing else.")
    assert "hello" in result.response.lower()

def test_file_write_tracked_in_result(self, tmp_path):
    """File writes appear in ProviderResult.files."""
    provider = GeminiCliProvider({
        "working_dir": str(tmp_path),
        "approval_mode": "yolo",
    })
    result = provider.generate(
        f"Create a file called test.txt containing 'test content'"
    )
    # Verify file was written
    assert (tmp_path / "test.txt").exists()
    # Verify tracked in result
    assert any("test.txt" in f for f in result.files.keys())

def test_file_edit_tracked_via_replace(self, tmp_path):
    """File edits via replace tool appear in ProviderResult.files."""
    # Create initial file
    test_file = tmp_path / "edit_me.txt"
    test_file.write_text("old content")

    provider = GeminiCliProvider({
        "working_dir": str(tmp_path),
        "approval_mode": "yolo",
    })
    result = provider.generate(
        "Edit edit_me.txt to change 'old' to 'new'"
    )
    # Verify file was modified
    assert "new content" in test_file.read_text()
    # Verify tracked in result
    assert any("edit_me.txt" in f for f in result.files.keys())

def test_model_config_applied(self):
    """Model config is passed to CLI."""
    provider = GeminiCliProvider({"model": "gemini-2.5-flash"})
    result = provider.generate("Say 'test'")
    assert result.response

def test_timeout_config_works(self):
    """timeout config limits execution time."""
    provider = GeminiCliProvider({"timeout": 1})  # 1 second
    # Long-running prompt should timeout
    with pytest.raises(ProviderError, match="timed out"):
        provider.generate("Count slowly from 1 to 1000, saying each number")

def test_file_based_prompt(self, tmp_path):
    """File-based prompt delivery works via context['prompt_file']."""
    # Write prompt to file
    prompt_file = tmp_path / "test-prompt.md"
    prompt_file.write_text("Say 'file prompt works' and nothing else.")

    provider = GeminiCliProvider({
        "working_dir": str(tmp_path),
        "approval_mode": "yolo",
    })
    result = provider.generate(
        prompt="ignored when file provided",
        context={"prompt_file": str(prompt_file)},
    )
    assert "file prompt works" in result.response.lower()
```

### pytest Marker Registration

**File:** `pytest.ini`

Add marker:
```ini
markers =
    gemini_cli: Tests requiring Gemini CLI (skip with '-m "not gemini_cli"')
```

### Acceptance Criteria
- [ ] Tests skip gracefully when CLI not installed
- [ ] Basic prompt/response flow works (stdin)
- [ ] File-based prompt delivery works
- [ ] File write tracking works with real files
- [ ] File edit tracking works with replace tool
- [ ] Config options are passed through
- [ ] Timeout works as expected
- [ ] pytest marker registered

---

## Phase 4: Registration

**Goal:** Register provider in factory and export from package.

**TDD:** No

### Spec

**Files to modify:**
1. `aiwf/domain/providers/__init__.py` - Import, register, export

### Registration

```python
# aiwf/domain/providers/__init__.py
from .response_provider import ResponseProvider, AIProvider
from .provider_factory import ResponseProviderFactory
from .manual_provider import ManualProvider
from .claude_code_provider import ClaudeCodeProvider
from .gemini_cli_provider import GeminiCliProvider  # NEW

# Backwards compatibility alias
ProviderFactory = ResponseProviderFactory

# Register built-in providers
ResponseProviderFactory.register("manual", ManualProvider)
ResponseProviderFactory.register("claude-code", ClaudeCodeProvider)
ResponseProviderFactory.register("gemini-cli", GeminiCliProvider)  # NEW

__all__ = [
    "ResponseProvider",
    "AIProvider",
    "ResponseProviderFactory",
    "ProviderFactory",
    "ManualProvider",
    "ClaudeCodeProvider",
    "GeminiCliProvider",  # NEW
]
```

### Circular Import Verification

After registration, verify no circular imports by running:

```bash
# Verify clean import
python -c "from aiwf.domain.providers import GeminiCliProvider; print('Import OK')"

# Verify factory works
python -c "from aiwf.domain.providers import ResponseProviderFactory; p = ResponseProviderFactory.create('gemini-cli'); print(f'Factory OK: {type(p).__name__}')"

# Verify full package import
python -c "import aiwf; print('Package OK')"
```

### Acceptance Criteria
- [ ] `from aiwf.domain.providers import GeminiCliProvider` works
- [ ] `ResponseProviderFactory.create("gemini-cli")` returns GeminiCliProvider
- [ ] `ResponseProviderFactory.list_providers()` includes "gemini-cli"
- [ ] No circular import issues (verified via commands above)

---

## Implementation Order

Execute phases sequentially. Each phase must complete before the next.

```
Phase 1 (Provider Implementation)
    │
    ▼
Phase 2 (Unit Tests)
    │
    ▼
Phase 3 (Integration Tests)
    │
    ▼
Phase 4 (Registration)
```

---

## Code Review Checklist

Use this checklist when reviewing implementation:

### Phase 1 Review
- [ ] Uses async subprocess (not sync subprocess.run)
- [ ] File-based prompts supported via `context["prompt_file"]` (preferred)
- [ ] Stdin fallback for prompts without prompt_file
- [ ] NDJSON parsing with per-line try/catch
- [ ] Malformed JSON logged with content sample
- [ ] Tracks both `write_file` and `replace` tools
- [ ] Only tracks files with `tool_result.status == "success"`
- [ ] Captures stderr even on success
- [ ] Timeout implemented via `asyncio.wait_for()`
- [ ] Config validation warns on unknown keys
- [ ] Config validation for `approval_mode` enum
- [ ] Config validation for list types (`include_directories`, `allowed_tools`)
- [ ] All config keys from ADR-0014 implemented
- [ ] Error messages include actionable instructions
- [ ] No `shell=True` in subprocess

### Phase 2 Review
- [ ] All NDJSON event types have dedicated tests
- [ ] Both file write tools tested (write_file, replace)
- [ ] File-based and stdin-based prompt delivery tested
- [ ] Failed tool_result handling tested
- [ ] Malformed JSON handling tested (including partial lines)
- [ ] Config validation tested (enum, list types)
- [ ] Timeout handling tested
- [ ] Auth error handling tested
- [ ] Mocks properly isolate subprocess
- [ ] No real CLI calls in unit tests
- [ ] Tests are deterministic

### Phase 3 Review
- [ ] Skip condition works when CLI not installed
- [ ] pytest marker registered
- [ ] Tests clean up created files (use tmp_path)
- [ ] Reasonable timeouts set
- [ ] Both write and edit operations tested
- [ ] File-based prompt delivery tested

### Phase 4 Review
- [ ] Factory registration follows existing pattern
- [ ] Export added to __all__
- [ ] Circular import verification commands executed
- [ ] All three verification commands pass

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Gemini CLI output format changes | Log raw output on parse failures, test against real CLI |
| Windows subprocess differences | Use list args (not shell), test on Windows |
| Large prompt handling | Use stdin, not command line args |
| No cost controls | Document limitation, use timeout as guard |
| Auth state expires | Clear error message with login instructions |

---

## Success Criteria

Implementation is complete when:

1. `GeminiCliProvider` supports file-based prompts (preferred) and stdin fallback
2. NDJSON parsing handles all event types with error recovery (including content samples)
3. Both `write_file` and `replace` tools tracked
4. Only successful writes tracked (via `tool_result.status`)
5. Config validation includes enum and list type checks
6. All config keys from ADR-0014 supported
7. Unit tests pass with mocked subprocess
8. Integration tests pass (when CLI available)
9. Provider registered as "gemini-cli"
10. Provider exported from `aiwf.domain.providers`
11. Circular import verification passes

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

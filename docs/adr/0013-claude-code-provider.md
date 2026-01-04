# ADR-0013: Claude Code AI Provider

**Status:** Draft
**Date:** January 2, 2025
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine supports manual mode where users copy prompts to AI interfaces and paste responses back. This works but is tedious for users with access to CLI-based AI agents.

Claude Code is Anthropic's CLI agent with local filesystem access, making it suitable for automated workflow execution. We need to implement a provider that integrates Claude Code for automated prompt/response handling.

**Goal:** Implement a Claude Code provider that automates prompt/response handling while maintaining manual mode as fallback.

---

## Decision Drivers

1. **OS Agnostic** - Must work on Windows, macOS, and Linux without platform-specific code
2. **Anthropic Alignment** - Follow Anthropic's recommended patterns for production automation
3. **Cost Control** - Users must be able to limit token usage and spending
4. **Simplicity** - Minimal changes to existing orchestrator and tests
5. **Flexibility** - Support per-phase configuration (different models/settings per workflow phase)

---

## Considered Options

### Option 1: CLI Subprocess

Invoke Claude Code via `subprocess.run(["claude", "-p", ...])`.

**Pros:**
- Simple implementation
- No additional Python dependencies

**Cons:**
- Windows installs Claude as `.CMD` batch file, requiring `shell=True`
- Platform-specific path handling needed
- String parsing for output
- Not aligned with Anthropic's recommendation for production

### Option 2: Claude Agent SDK

Use the official `claude-agent-sdk` Python package.

**Pros:**
- OS agnostic (SDK handles platform differences)
- Typed message objects instead of string parsing
- Aligned with Anthropic's recommendation for production automation
- Native async support
- Session continuity and hooks available for future use

**Cons:**
- Additional Python dependency
- SDK is async-only (requires wrapper for sync interface)

### Option 3: Direct Anthropic API

Use the `anthropic` Python package to call Claude API directly.

**Pros:**
- Full control over API calls
- No CLI dependency

**Cons:**
- Loses Claude Code's filesystem access and tools
- Would require implementing file handling ourselves
- Different authentication model (API key vs CLI login)

---

## Decision Outcome

**Chosen option: Option 2 (Claude Agent SDK)**

The SDK provides the best balance of capability and maintainability. It eliminates platform-specific code and aligns with Anthropic's recommended approach for production automation.

**Anthropic's guidance by use case:**

| Use Case | Anthropic Recommends |
|----------|---------------------|
| One-off scripted tasks | CLI with `-p` flag |
| CI/CD pipelines | SDK (preferred) |
| Custom applications | SDK (preferred) |
| Production automation | SDK (strongly preferred) |

---

## Design Decisions

### Authentication

The SDK wraps the Claude Code CLI and inherits credentials from `claude login`. No `ANTHROPIC_API_KEY` environment variable is required.

**Rationale:** Same security boundary as Claude Code itself. Users authenticate once via CLI, all SDK calls use those credentials.

---

### Async Handling

The SDK is async-only. Use `asyncio.run()` wrapper in provider to maintain sync interface:

```python
def generate(self, prompt: str, context: dict) -> str | None:
    return asyncio.run(self._async_generate(prompt, context))

async def _async_generate(self, prompt: str, context: dict) -> str | None:
    async for message in query(prompt=prompt, options=self.options):
        # ... collect response
```

**Rationale (vs making orchestrator async):**
- Async handling isolated to provider (~20 lines)
- Orchestrator, CLI, and tests remain synchronous
- Overhead of event loop creation negligible compared to API latency
- Can migrate to full async later if concurrent provider calls needed

**Note:** If orchestrator becomes async in future, replace `asyncio.run()` with direct `await` to avoid nested event loop issues.

---

### Session Continuity

Skip SDK session continuity for MVP.

The SDK supports `resume=session_id` to maintain conversation context across calls. We will not use this feature initially.

**Rationale:**
- Workflow design assumes different AI providers per phase is valid
- Current architecture has no session concept across phases
- Adding sessions adds complexity without clear benefit
- Can be added as configuration option later if users request it

---

### Configuration Options

Support per-phase configuration with cost/token controls.

**Direct SDK parameters:**

| Config Key | Maps To | Purpose |
|------------|---------|---------|
| `model` | `ClaudeAgentOptions.model` | Model selection (sonnet, opus) |
| `allowed_tools` | `ClaudeAgentOptions.allowed_tools` | Tool whitelist |
| `permission_mode` | `ClaudeAgentOptions.permission_mode` | Edit approval mode |
| `working_dir` | `ClaudeAgentOptions.cwd` | Working directory for Claude |
| `max_turns` | `ClaudeAgentOptions.max_turns` | Maximum agent iterations |
| `add_dirs` | `ClaudeAgentOptions.add_dirs` | Additional context directories |

**Passed via SDK's `env` parameter:**

| Config Key | Environment Variable | Purpose |
|------------|---------------------|---------|
| `max_output_tokens` | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Output token limit (default: 32000) |
| `max_thinking_tokens` | `MAX_THINKING_TOKENS` | Extended thinking budget (0 = disabled) |

**Passed via SDK's `extra_args` parameter:**

| Config Key | CLI Flag | Purpose |
|------------|----------|---------|
| `max_budget_usd` | `--max-budget-usd` | Cost limit per invocation |

**Implementation:**

```python
options = ClaudeAgentOptions(
    model=config.get("model"),
    allowed_tools=config.get("allowed_tools", ["Read", "Write", "Grep", "Glob"]),
    permission_mode=config.get("permission_mode", "acceptEdits"),
    cwd=config.get("working_dir"),
    max_turns=config.get("max_turns"),
    add_dirs=config.get("add_dirs", []),
    env={
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(config["max_output_tokens"]),
        "MAX_THINKING_TOKENS": str(config["max_thinking_tokens"]),
    } if config.get("max_output_tokens") or config.get("max_thinking_tokens") else {},
    extra_args={
        "--max-budget-usd": str(config["max_budget_usd"]),
    } if config.get("max_budget_usd") else {},
)
```

**Per-Phase Configuration:**

Provider is created fresh per-call (not kept alive). This enables phase-specific configuration:

```yaml
providers:
  claude-code:
    default:
      max_budget_usd: 1.00
    phases:
      plan:
        model: opus
        max_thinking_tokens: 10000
      review:
        model: sonnet
        max_thinking_tokens: 0
      generate:
        model: sonnet
        max_thinking_tokens: 5000
```

Orchestrator passes phase-specific config to factory at provider creation time.

---

### Integration with Approval Providers

`ClaudeCodeAIProvider` implements `AIProvider` only. For approval use, wrap with `AIApprovalProvider`.

This follows the existing Adapter pattern where `AIApprovalProvider` wraps any `AIProvider`:

```
ClaudeCodeAIProvider (AIProvider)
        │
        │ wrapped by
        ▼
AIApprovalProvider (ApprovalProvider)
```

The `ApprovalProviderFactory` handles this automatically for non-builtin provider keys.

**Rationale:**
- Single Responsibility - provider just generates, approval logic is separate
- Composition over inheritance
- No duplicate implementation needed

---

## Provider Interface

```python
class ClaudeCodeAIProvider(AIProvider):
    """Claude Code AI provider using the Agent SDK."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize with optional configuration."""

    def validate(self) -> None:
        """Verify Claude Code CLI is available."""

    def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str | None:
        """Generate response using Claude Code Agent SDK."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata."""
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
            ],
            "default_response_timeout": 600,
            "fs_ability": "local-write",
        }
```

---

### File Write Tracking

Claude Code writes files directly to disk via its `Write` tool. To track these for `AIProviderResult.files`:

1. Parse `ToolUseBlock` messages where `name == "Write"`
2. Extract `file_path` from tool input
3. Return `{file_path: None}` indicating provider wrote directly

This matches ADR-0011 convention: `None` value = provider wrote file directly.

```python
files_written: dict[str, None] = {}

async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock) and block.name == "Write":
                file_path = block.input.get("file_path")
                if file_path:
                    files_written[file_path] = None

return AIProviderResult(response=response_text, files=files_written)
```

---

## Error Handling

| Condition | Handling |
|-----------|----------|
| SDK not installed | `ImportError` in `validate()`, raise `ProviderError` with install instructions |
| Claude CLI not installed | `CLINotFoundError` from SDK, wrapped as `ProviderError` |
| SDK process error | `ProcessError` from SDK, wrapped as `ProviderError` with stderr if available |
| Response parsing error | `CLIJSONDecodeError` from SDK, wrapped as `ProviderError` |
| Max turns exceeded | SDK returns with partial result, log warning |
| Empty response | Return empty string (profile handles validation) |

**Logging:** Capture SDK stderr/debug output for partial failures. Log at WARNING level for recoverable issues, ERROR for failures.

---

## Dependencies

| Dependency | Type | Description |
|------------|------|-------------|
| `claude-agent-sdk` | Python package | Official Anthropic SDK for Claude Code |
| Claude Code CLI | Runtime | Must be installed and authenticated |
| ADR-0007 | Architecture | Provider plugin infrastructure |
| ADR-0012 | Architecture | Approval provider pattern |

---

## Implementation Plan

| Task | Priority | Notes |
|------|----------|-------|
| Add `claude-agent-sdk` to dependencies | High | pyproject.toml |
| Implement `ClaudeCodeAIProvider` with SDK | High | SDK-based implementation |
| Add config options (tokens, budget, thinking) | High | Verify SDK parameter names |
| Create unit tests | High | Mock SDK calls |
| Register provider in factory | Medium | AIProviderFactory |
| Create integration tests | Medium | Real SDK invocation |

---

## Resolved Questions

1. **SDK parameter names:** ✅ Resolved. Token/budget controls are not direct SDK parameters. Use `env` for environment variables and `extra_args` for CLI flags. Only `max_turns` is a direct parameter.

2. **Timeout configuration:** ✅ Resolved. SDK provides `max_turns` for iteration limits. No direct timeout parameter; rely on external timeout handling if needed.

3. **File write tracking:** ✅ Resolved. Parse `ToolUseBlock` messages with `name == "Write"` to track files written by Claude.

---

## Related Decisions

- **ADR-0007:** Plugin architecture (provider infrastructure)
- **ADR-0012:** Approval providers (AIApprovalProvider wraps ResponseProvider)
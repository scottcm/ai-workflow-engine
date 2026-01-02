"""Claude Code response provider using the Claude Agent SDK.

Uses the official claude-agent-sdk package for OS-agnostic Claude Code integration.
This eliminates platform-specific code and aligns with Anthropic's recommended
approach for production automation.

Claude Code is a local-write provider: it writes files directly using
its Write tool. The engine validates files exist after execution.
"""

import asyncio
import shutil
import warnings
from typing import Any

from aiwf.domain.errors import ProviderError
from aiwf.domain.models.provider_result import ProviderResult
from aiwf.domain.providers.response_provider import ResponseProvider


# Default tools for Claude Code - includes Write for file creation
DEFAULT_ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Write"]


class ClaudeCodeProvider(ResponseProvider):
    """Response provider using Claude Agent SDK.

    Uses the official claude-agent-sdk package for cross-platform Claude Code
    integration. The SDK handles platform differences internally.

    Requirements:
        - claude-agent-sdk package must be installed
        - Claude Code CLI must be installed and authenticated (via `claude login`)

    Configuration (Direct SDK parameters):
        - model: Model to use (e.g., "sonnet", "opus")
        - allowed_tools: List of tools to allow (default: Read,Grep,Glob,Write)
        - permission_mode: Permission mode (default: acceptEdits for automation)
        - working_dir: Working directory for Claude
        - max_turns: Maximum agent iterations
        - add_dirs: Additional directories for context

    Configuration (Via environment variables):
        - max_output_tokens: Output token limit (default: 32000)
        - max_thinking_tokens: Extended thinking budget (0 = disabled)

    Configuration (Via CLI flags):
        - max_budget_usd: Cost limit per invocation

    Example:
        provider = ClaudeCodeProvider({
            "model": "sonnet",
            "max_budget_usd": 1.00,
            "max_thinking_tokens": 5000,
        })
        result = provider.generate("Generate Entity.java")
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the Claude Code provider.

        Args:
            config: Optional configuration dictionary with keys:
                - model: Model alias or full name (e.g., "sonnet", "opus")
                - allowed_tools: List of tools to allow (default includes Write)
                - permission_mode: Permission mode for the session
                - working_dir: Working directory for Claude
                - max_turns: Maximum agent iterations
                - add_dirs: Additional directories to add for context
                - max_output_tokens: Output token limit
                - max_thinking_tokens: Extended thinking budget (0 = disabled)
                - max_budget_usd: Cost limit per invocation
        """
        self.config = config or {}
        self._validate_config()

        self._model = self.config.get("model")
        self._allowed_tools = self.config.get("allowed_tools", DEFAULT_ALLOWED_TOOLS)
        self._permission_mode = self.config.get("permission_mode", "acceptEdits")
        self._working_dir = self.config.get("working_dir")
        self._max_turns = self.config.get("max_turns")
        self._add_dirs: list[str] = self.config.get("add_dirs", [])
        self._max_output_tokens = self.config.get("max_output_tokens")
        self._max_thinking_tokens = self.config.get("max_thinking_tokens")
        self._max_budget_usd = self.config.get("max_budget_usd")

    def _validate_config(self) -> None:
        """Validate configuration and warn on unknown keys.

        Raises:
            ValueError: If config values are invalid (e.g., negative max_turns)
        """
        if not self.config:
            return

        # Warn on unknown config keys
        known_keys = set(self.get_metadata()["config_keys"])
        unknown_keys = set(self.config.keys()) - known_keys
        if unknown_keys:
            warnings.warn(
                f"Unknown ClaudeCodeProvider config keys ignored: {sorted(unknown_keys)}",
                UserWarning,
                stacklevel=3,
            )

        # Validate numeric constraints
        max_turns = self.config.get("max_turns")
        if max_turns is not None and max_turns < 1:
            raise ValueError("max_turns must be >= 1")

        max_budget = self.config.get("max_budget_usd")
        if max_budget is not None and max_budget <= 0:
            raise ValueError("max_budget_usd must be > 0")

        max_output = self.config.get("max_output_tokens")
        if max_output is not None and max_output < 1:
            raise ValueError("max_output_tokens must be >= 1")

        max_thinking = self.config.get("max_thinking_tokens")
        if max_thinking is not None and max_thinking < 0:
            raise ValueError("max_thinking_tokens must be >= 0")

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
                "working_dir",
                "max_turns",
                "add_dirs",
                "max_output_tokens",
                "max_thinking_tokens",
                "max_budget_usd",
            ],
            "default_connection_timeout": 30,  # SDK handles connection
            "default_response_timeout": 600,  # 10 minutes for complex tasks
            "fs_ability": "local-write",  # Claude Code has file access
            "supports_system_prompt": True,
            "supports_file_attachments": False,
        }

    def validate(self) -> None:
        """Verify SDK and CLI are available.

        Raises:
            ProviderError: If SDK not installed or CLI not found
        """
        # Check SDK is installed
        try:
            from claude_agent_sdk import query  # noqa: F401
        except ImportError:
            raise ProviderError(
                "claude-agent-sdk not installed. "
                "Install with: pip install claude-agent-sdk"
            )

        # Check CLI is available (SDK validates internally, but check early)
        if shutil.which("claude") is None:
            raise ProviderError(
                "Claude Code CLI not found. "
                "Install from: https://docs.anthropic.com/claude-code"
            )

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> ProviderResult:
        """Generate response using Claude Agent SDK.

        Uses asyncio.run() to wrap the async SDK in a sync interface.

        Args:
            prompt: The prompt text to send to Claude
            context: Optional context dictionary with:
                - session_dir: Path to session directory
                - project_root: Path to project root
            system_prompt: Optional system prompt (passed via SDK)
            connection_timeout: Not used (SDK handles internally)
            response_timeout: Not used (SDK handles via max_turns)

        Returns:
            ProviderResult with:
                - response: Text response from Claude
                - files: Dict of files written (path -> None for SDK-written files)

        Raises:
            ProviderError: If SDK fails
        """
        return asyncio.run(self._async_generate(prompt, context, system_prompt))

    async def _async_generate(
        self,
        prompt: str,
        context: dict[str, Any] | None,
        system_prompt: str | None,
    ) -> ProviderResult:
        """Async implementation using Claude Agent SDK.

        Args:
            prompt: The prompt text
            context: Optional context with paths
            system_prompt: Optional system prompt

        Returns:
            ProviderResult with response and files written
        """
        try:
            from claude_agent_sdk import query, ClaudeAgentOptions
            from claude_agent_sdk.types import AssistantMessage, ToolUseBlock
        except ImportError:
            raise ProviderError(
                "claude-agent-sdk not installed. "
                "Install with: pip install claude-agent-sdk"
            )

        options = self._build_options(context, system_prompt)

        response_text = ""
        files_written: dict[str, None] = {}

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        # Collect text response
                        if hasattr(block, "text"):
                            response_text += block.text

                        # Track file writes via ToolUseBlock
                        if isinstance(block, ToolUseBlock) and block.name == "Write":
                            file_path = block.input.get("file_path")
                            if file_path:
                                files_written[file_path] = None

        except Exception as e:
            # Handle known SDK exceptions with actionable messages
            raise self._wrap_sdk_error(e)

        return ProviderResult(response=response_text, files=files_written)

    def _build_options(
        self,
        context: dict[str, Any] | None,
        system_prompt: str | None,
    ) -> "ClaudeAgentOptions":
        """Build ClaudeAgentOptions from config and context.

        Args:
            context: Optional context with paths
            system_prompt: Optional system prompt

        Returns:
            Configured ClaudeAgentOptions
        """
        from claude_agent_sdk import ClaudeAgentOptions

        # Collect add_dirs from config and context
        add_dirs = list(self._add_dirs)
        if context:
            if context.get("session_dir"):
                add_dirs.append(str(context["session_dir"]))
            if context.get("project_root"):
                add_dirs.append(str(context["project_root"]))

        # Resolve working directory
        cwd = self._working_dir
        if not cwd and context and context.get("project_root"):
            cwd = str(context["project_root"])

        # Build environment variables for token controls
        env: dict[str, str] = {}
        if self._max_output_tokens is not None:
            env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(self._max_output_tokens)
        if self._max_thinking_tokens is not None:
            env["MAX_THINKING_TOKENS"] = str(self._max_thinking_tokens)

        # Build extra_args for CLI flags (dict format: flag -> value)
        extra_args: dict[str, str] = {}
        if self._max_budget_usd is not None:
            extra_args["--max-budget-usd"] = str(self._max_budget_usd)

        return ClaudeAgentOptions(
            model=self._model,
            allowed_tools=self._allowed_tools,
            permission_mode=self._permission_mode,
            cwd=cwd,
            max_turns=self._max_turns,
            add_dirs=add_dirs if add_dirs else None,
            system_prompt=system_prompt,
            env=env,  # SDK requires dict (can be empty, but not None)
            extra_args=extra_args,  # SDK requires dict (can be empty)
        )

    def _wrap_sdk_error(self, error: Exception) -> ProviderError:
        """Wrap SDK exceptions with actionable error messages.

        Args:
            error: The exception from the SDK

        Returns:
            ProviderError with actionable message
        """
        error_type = type(error).__name__

        # Handle known SDK exceptions with specific messages
        if error_type == "CLINotFoundError":
            return ProviderError(
                "Claude Code CLI not found. "
                "Install from: https://docs.anthropic.com/claude-code"
            )
        elif error_type == "ProcessError":
            return ProviderError(f"Claude Code process failed: {error}")
        elif error_type == "CLIJSONDecodeError":
            return ProviderError(
                f"Invalid response from Claude Code CLI (malformed JSON): {error}"
            )
        elif error_type == "TimeoutError" or "timeout" in str(error).lower():
            return ProviderError(
                f"Claude Code timed out. Consider increasing max_turns or max_budget_usd: {error}"
            )
        else:
            # Generic fallback for unknown exceptions
            return ProviderError(f"Claude Agent SDK error ({error_type}): {error}")

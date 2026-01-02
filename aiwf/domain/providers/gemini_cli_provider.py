"""Gemini CLI response provider using subprocess.

Uses Gemini CLI with stream-json output format for structured parsing.
Tracks file writes via tool_use/tool_result events.

Gemini CLI is a local-write provider: it writes files directly using
its write_file and replace tools. The engine validates files exist after execution.
"""

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

# Valid approval modes
VALID_APPROVAL_MODES = {"default", "auto_edit", "yolo"}

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
        """Initialize provider with optional configuration.

        Args:
            config: Optional configuration dictionary with keys:
                - model: Model to use
                - sandbox: Enable sandbox mode
                - approval_mode: Approval mode (default, auto_edit, yolo)
                - include_directories: Additional workspace directories
                - allowed_tools: Tools allowed without confirmation
                - working_dir: Working directory for CLI
                - timeout: Process timeout in seconds
        """
        self.config = config or {}
        self._validate_config()

        self._model = self.config.get("model")
        self._sandbox = self.config.get("sandbox", False)
        self._approval_mode = self.config.get("approval_mode", "yolo")
        self._include_directories: list[str] = self.config.get("include_directories", [])
        self._allowed_tools: list[str] | None = self.config.get("allowed_tools")
        self._working_dir = self.config.get("working_dir")
        self._timeout = self.config.get("timeout", DEFAULT_TIMEOUT)

    def _validate_config(self) -> None:
        """Validate configuration and warn on unknown keys.

        Raises:
            ValueError: If config values are invalid
        """
        if not self.config:
            return

        # Warn on unknown config keys
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
        if approval_mode is not None and approval_mode not in VALID_APPROVAL_MODES:
            raise ValueError(
                f"approval_mode must be one of {sorted(VALID_APPROVAL_MODES)}, "
                f"got: {approval_mode!r}"
            )

        # Validate list types
        for key in ("include_directories", "allowed_tools"):
            value = self.config.get(key)
            if value is not None and not isinstance(value, list):
                raise ValueError(f"{key} must be a list, got: {type(value).__name__}")

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
            "default_response_timeout": DEFAULT_TIMEOUT,
            "fs_ability": "local-write",
        }

    def validate(self) -> None:
        """Verify Gemini CLI is available.

        Raises:
            ProviderError: If Gemini CLI is not installed
        """
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
        """Generate response using Gemini CLI subprocess.

        Args:
            prompt: The prompt to send to Gemini
            context: Optional context dict, may contain:
                - prompt_file: Path to prompt file (preferred over stdin)
                - project_root: Working directory fallback
            system_prompt: Optional system prompt (prepended when using stdin)
            connection_timeout: Unused (subprocess-based)
            response_timeout: Unused (uses config timeout)

        Returns:
            ProviderResult with response text and files written
        """
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

        # Determine prompt content
        # File-based prompts: tell Gemini to read the file (avoids arg length limits)
        prompt_file = context.get("prompt_file") if context else None
        if prompt_file:
            # Let Gemini read the file itself - cleaner and handles large prompts
            file_prompt = f"Process the prompt in {prompt_file}"
            if system_prompt:
                file_prompt = f"{system_prompt}\n\n{file_prompt}"
            args.extend(["-p", file_prompt])
            logger.debug(f"Directing Gemini to read prompt file: {prompt_file}")
        else:
            # Direct prompt via -p flag
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            args.extend(["-p", full_prompt])
            logger.debug("Using direct prompt via -p flag")

        try:
            process = await asyncio.create_subprocess_exec(
                "gemini",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            # Wait for process completion with timeout
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
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
        """Build CLI arguments from config.

        Args:
            context: Optional context dict

        Returns:
            List of CLI arguments
        """
        args = ["-o", "stream-json"]

        # Approval mode (default to yolo for automation)
        if self._approval_mode == "yolo":
            args.append("-y")
        elif self._approval_mode and self._approval_mode != "default":
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
        """Parse NDJSON stream and extract response and file writes.

        Args:
            stdout: Raw stdout bytes from subprocess

        Returns:
            Tuple of (response_text, files_written dict)
        """
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
            logger.warning(
                f"Malformed JSON lines ({len(parse_errors)}): {parse_errors[:3]}"
            )

        return response_text, files_written

    def _wrap_process_error(self, returncode: int, stderr: str) -> ProviderError:
        """Wrap subprocess errors with actionable messages.

        Args:
            returncode: Process exit code
            stderr: Standard error output

        Returns:
            ProviderError with actionable message
        """
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

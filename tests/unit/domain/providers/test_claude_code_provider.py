"""Unit tests for ClaudeCodeProvider.

Tests use mocked claude-agent-sdk to avoid requiring Claude Code CLI.
"""

from typing import Any
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

import pytest

from aiwf.domain.errors import ProviderError
from aiwf.domain.models.provider_result import ProviderResult
from aiwf.domain.providers.claude_code_provider import ClaudeCodeProvider, DEFAULT_ALLOWED_TOOLS


class TestClaudeCodeProviderMetadata:
    """Tests for provider metadata."""

    def test_metadata_has_required_fields(self):
        """Provider metadata includes all required fields."""
        metadata = ClaudeCodeProvider.get_metadata()

        assert metadata["name"] == "claude-code"
        assert "description" in metadata
        assert metadata["requires_config"] is False
        assert isinstance(metadata["config_keys"], list)
        assert metadata["default_connection_timeout"] == 30
        assert metadata["default_response_timeout"] == 600

    def test_metadata_has_capability_fields(self):
        """Provider metadata includes capability fields."""
        metadata = ClaudeCodeProvider.get_metadata()

        assert metadata["supports_system_prompt"] is True
        assert metadata["fs_ability"] == "local-write"

    def test_metadata_includes_all_config_keys(self):
        """Provider metadata lists all supported config keys."""
        metadata = ClaudeCodeProvider.get_metadata()
        config_keys = metadata["config_keys"]

        # Direct SDK parameters
        assert "model" in config_keys
        assert "allowed_tools" in config_keys
        assert "permission_mode" in config_keys
        assert "working_dir" in config_keys
        assert "max_turns" in config_keys
        assert "add_dirs" in config_keys

        # Via environment variables
        assert "max_output_tokens" in config_keys
        assert "max_thinking_tokens" in config_keys

        # Via CLI flags
        assert "max_budget_usd" in config_keys


class TestClaudeCodeProviderValidation:
    """Tests for validate() method."""

    @patch("aiwf.domain.providers.claude_code_provider.shutil.which")
    def test_validate_succeeds_when_sdk_and_cli_available(self, mock_which):
        """validate() passes when SDK importable and CLI in PATH."""
        mock_which.return_value = "/usr/local/bin/claude"

        provider = ClaudeCodeProvider()
        provider.validate()  # Should not raise

        mock_which.assert_called_once_with("claude")

    @patch("aiwf.domain.providers.claude_code_provider.shutil.which")
    def test_validate_raises_when_cli_not_found(self, mock_which):
        """validate() raises ProviderError when CLI not in PATH."""
        mock_which.return_value = None

        provider = ClaudeCodeProvider()

        with pytest.raises(ProviderError) as exc_info:
            provider.validate()

        assert "Claude Code CLI not found" in str(exc_info.value)


class TestClaudeCodeProviderConfig:
    """Tests for provider configuration."""

    def test_default_config(self):
        """Provider works with default configuration."""
        provider = ClaudeCodeProvider()

        assert provider._model is None
        assert provider._allowed_tools == DEFAULT_ALLOWED_TOOLS
        assert "Write" in provider._allowed_tools  # Write is required for file creation
        assert provider._permission_mode == "acceptEdits"  # Required for automation

    def test_custom_config(self):
        """Provider accepts custom configuration."""
        config = {
            "model": "sonnet",
            "allowed_tools": ["Read", "Write"],
            "permission_mode": "acceptEdits",
            "add_dirs": ["/extra/path"],
            "max_turns": 10,
            "max_output_tokens": 16000,
            "max_thinking_tokens": 5000,
            "max_budget_usd": 1.50,
        }
        provider = ClaudeCodeProvider(config)

        assert provider._model == "sonnet"
        assert provider._allowed_tools == ["Read", "Write"]
        assert provider._permission_mode == "acceptEdits"
        assert provider._add_dirs == ["/extra/path"]
        assert provider._max_turns == 10
        assert provider._max_output_tokens == 16000
        assert provider._max_thinking_tokens == 5000
        assert provider._max_budget_usd == 1.50

    def test_unknown_config_keys_emit_warning(self):
        """Unknown config keys trigger UserWarning."""
        config = {
            "model": "sonnet",
            "unknown_key": "value",
            "another_unknown": 123,
        }

        with pytest.warns(UserWarning, match="Unknown ClaudeCodeProvider config keys"):
            provider = ClaudeCodeProvider(config)

        # Known keys still work
        assert provider._model == "sonnet"

    def test_invalid_max_turns_raises_value_error(self):
        """max_turns < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            ClaudeCodeProvider({"max_turns": 0})

        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            ClaudeCodeProvider({"max_turns": -5})

    def test_invalid_max_budget_raises_value_error(self):
        """max_budget_usd <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_budget_usd must be > 0"):
            ClaudeCodeProvider({"max_budget_usd": 0})

        with pytest.raises(ValueError, match="max_budget_usd must be > 0"):
            ClaudeCodeProvider({"max_budget_usd": -1.0})

    def test_invalid_max_output_tokens_raises_value_error(self):
        """max_output_tokens < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_output_tokens must be >= 1"):
            ClaudeCodeProvider({"max_output_tokens": 0})

    def test_invalid_max_thinking_tokens_raises_value_error(self):
        """max_thinking_tokens < 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_thinking_tokens must be >= 0"):
            ClaudeCodeProvider({"max_thinking_tokens": -1})

    def test_max_thinking_tokens_zero_is_valid(self):
        """max_thinking_tokens = 0 is valid (disables thinking)."""
        provider = ClaudeCodeProvider({"max_thinking_tokens": 0})
        assert provider._max_thinking_tokens == 0


class TestClaudeCodeProviderBuildOptions:
    """Tests for _build_options() method - SDK options configuration."""

    def test_build_options_maps_model(self):
        """model config maps to ClaudeAgentOptions.model."""
        provider = ClaudeCodeProvider({"model": "opus"})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.model == "opus"

    def test_build_options_maps_allowed_tools(self):
        """allowed_tools config maps to ClaudeAgentOptions.allowed_tools."""
        provider = ClaudeCodeProvider({"allowed_tools": ["Read", "Write", "Bash"]})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.allowed_tools == ["Read", "Write", "Bash"]

    def test_build_options_maps_permission_mode(self):
        """permission_mode maps to ClaudeAgentOptions.permission_mode."""
        provider = ClaudeCodeProvider({"permission_mode": "bypassPermissions"})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.permission_mode == "bypassPermissions"

    def test_build_options_maps_working_dir_to_cwd(self):
        """working_dir config maps to ClaudeAgentOptions.cwd."""
        provider = ClaudeCodeProvider({"working_dir": "/my/project"})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.cwd == "/my/project"

    def test_build_options_uses_context_project_root_as_cwd(self):
        """Context project_root is used as cwd when working_dir not set."""
        provider = ClaudeCodeProvider()
        context = {"project_root": "/context/project"}
        options = provider._build_options(context=context, system_prompt=None)

        assert options.cwd == "/context/project"

    def test_build_options_working_dir_takes_priority(self):
        """Configured working_dir takes priority over context project_root."""
        provider = ClaudeCodeProvider({"working_dir": "/config/project"})
        context = {"project_root": "/context/project"}
        options = provider._build_options(context=context, system_prompt=None)

        assert options.cwd == "/config/project"

    def test_build_options_maps_max_turns(self):
        """max_turns maps directly to SDK parameter."""
        provider = ClaudeCodeProvider({"max_turns": 15})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.max_turns == 15

    def test_build_options_maps_add_dirs(self):
        """add_dirs maps to ClaudeAgentOptions.add_dirs."""
        provider = ClaudeCodeProvider({"add_dirs": ["/dir1", "/dir2"]})
        options = provider._build_options(context=None, system_prompt=None)

        assert "/dir1" in options.add_dirs
        assert "/dir2" in options.add_dirs

    def test_build_options_combines_add_dirs_with_context(self):
        """add_dirs from config combines with context paths."""
        provider = ClaudeCodeProvider({"add_dirs": ["/config/dir"]})
        context = {"session_dir": "/session", "project_root": "/project"}
        options = provider._build_options(context=context, system_prompt=None)

        assert "/config/dir" in options.add_dirs
        assert "/session" in options.add_dirs
        assert "/project" in options.add_dirs

    def test_build_options_maps_system_prompt(self):
        """system_prompt is passed to ClaudeAgentOptions."""
        provider = ClaudeCodeProvider()
        options = provider._build_options(context=None, system_prompt="Be helpful")

        assert options.system_prompt == "Be helpful"

    def test_build_options_maps_max_output_tokens_to_env(self):
        """max_output_tokens passed via env dict."""
        provider = ClaudeCodeProvider({"max_output_tokens": 16000})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "16000"

    def test_build_options_maps_max_thinking_tokens_to_env(self):
        """max_thinking_tokens passed via env dict."""
        provider = ClaudeCodeProvider({"max_thinking_tokens": 5000})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.env["MAX_THINKING_TOKENS"] == "5000"

    def test_build_options_maps_max_budget_to_extra_args(self):
        """max_budget_usd passed via extra_args dict."""
        provider = ClaudeCodeProvider({"max_budget_usd": 2.50})
        options = provider._build_options(context=None, system_prompt=None)

        assert options.extra_args["--max-budget-usd"] == "2.5"

    def test_build_options_empty_env_when_no_token_configs(self):
        """env dict is empty when no token configs set."""
        provider = ClaudeCodeProvider()
        options = provider._build_options(context=None, system_prompt=None)

        assert options.env == {}

    def test_build_options_empty_extra_args_when_no_budget(self):
        """extra_args is empty when no budget config set."""
        provider = ClaudeCodeProvider()
        options = provider._build_options(context=None, system_prompt=None)

        assert options.extra_args == {}


class TestClaudeCodeProviderGenerate:
    """Tests for generate() method with mocked SDK."""

    def _create_mock_assistant_message(self, text_blocks: list[str], write_blocks: list[dict] | None = None):
        """Helper to create a mock AssistantMessage with text and optional Write blocks."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        # Create text content blocks
        content = []
        for text in text_blocks:
            mock_text = Mock()
            mock_text.text = text
            content.append(mock_text)

        # Create write tool blocks
        if write_blocks:
            for wb in write_blocks:
                mock_write = Mock(spec=ToolUseBlock)
                mock_write.name = "Write"
                mock_write.input = wb
                content.append(mock_write)

        # Create the message - use real class for isinstance check
        message = Mock(spec=AssistantMessage)
        message.content = content
        return message

    def test_generate_returns_provider_result(self):
        """generate() returns ProviderResult with response."""
        from claude_agent_sdk.types import AssistantMessage

        # Create mock message
        mock_text = Mock()
        mock_text.text = "Test response from Claude"

        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = [mock_text]

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("claude_agent_sdk.query", side_effect=mock_query):
            provider = ClaudeCodeProvider()
            result = provider.generate("Test prompt")

            assert isinstance(result, ProviderResult)
            assert result.response == "Test response from Claude"
            assert result.files == {}

    def test_generate_calls_sdk_with_prompt(self):
        """generate() calls query() with prompt."""
        from claude_agent_sdk.types import AssistantMessage

        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = []

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("claude_agent_sdk.query", side_effect=mock_query) as mock_q:
            provider = ClaudeCodeProvider()
            provider.generate("My test prompt")

            mock_q.assert_called_once()
            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["prompt"] == "My test prompt"

    def test_generate_tracks_file_writes(self):
        """generate() tracks Write tool uses in ProviderResult.files."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        # Create mock ToolUseBlock for Write
        mock_write_block = Mock(spec=ToolUseBlock)
        mock_write_block.name = "Write"
        mock_write_block.input = {"file_path": "/path/to/Entity.java"}

        # Create mock text block
        mock_text_block = Mock()
        mock_text_block.text = "Created the file"

        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = [mock_text_block, mock_write_block]

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("claude_agent_sdk.query", side_effect=mock_query):
            provider = ClaudeCodeProvider()
            result = provider.generate("Create Entity.java")

            # File should be tracked with None value (provider wrote it)
            assert "/path/to/Entity.java" in result.files
            assert result.files["/path/to/Entity.java"] is None

    def test_generate_handles_empty_response(self):
        """generate() returns empty string for no text blocks."""
        from claude_agent_sdk.types import AssistantMessage

        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = []

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("claude_agent_sdk.query", side_effect=mock_query):
            provider = ClaudeCodeProvider()
            result = provider.generate("Test prompt")

            assert result.response == ""
            assert result.files == {}

    def test_generate_handles_multiple_messages(self):
        """generate() concatenates text from multiple messages."""
        from claude_agent_sdk.types import AssistantMessage

        mock_text1 = Mock()
        mock_text1.text = "First part. "

        mock_text2 = Mock()
        mock_text2.text = "Second part."

        mock_message1 = Mock(spec=AssistantMessage)
        mock_message1.content = [mock_text1]

        mock_message2 = Mock(spec=AssistantMessage)
        mock_message2.content = [mock_text2]

        async def mock_query(*args, **kwargs):
            yield mock_message1
            yield mock_message2

        with patch("claude_agent_sdk.query", side_effect=mock_query):
            provider = ClaudeCodeProvider()
            result = provider.generate("Test prompt")

            assert result.response == "First part. Second part."

    def test_generate_tracks_multiple_write_blocks(self):
        """generate() tracks multiple Write blocks in single message."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        # Create mock ToolUseBlocks for multiple Write operations
        mock_write1 = Mock(spec=ToolUseBlock)
        mock_write1.name = "Write"
        mock_write1.input = {"file_path": "/path/to/Entity.java"}

        mock_write2 = Mock(spec=ToolUseBlock)
        mock_write2.name = "Write"
        mock_write2.input = {"file_path": "/path/to/Repository.java"}

        mock_write3 = Mock(spec=ToolUseBlock)
        mock_write3.name = "Write"
        mock_write3.input = {"file_path": "/path/to/Service.java"}

        mock_text = Mock()
        mock_text.text = "Created all files"

        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = [mock_text, mock_write1, mock_write2, mock_write3]

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("claude_agent_sdk.query", side_effect=mock_query):
            provider = ClaudeCodeProvider()
            result = provider.generate("Create Entity, Repository, Service")

            # All files should be tracked
            assert len(result.files) == 3
            assert "/path/to/Entity.java" in result.files
            assert "/path/to/Repository.java" in result.files
            assert "/path/to/Service.java" in result.files

    def test_generate_handles_mixed_text_and_tool_blocks(self):
        """generate() correctly handles interleaved text and tool blocks."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        # Interleaved text and write blocks
        mock_text1 = Mock()
        mock_text1.text = "Creating Entity.java... "

        mock_write1 = Mock(spec=ToolUseBlock)
        mock_write1.name = "Write"
        mock_write1.input = {"file_path": "/path/to/Entity.java"}

        mock_text2 = Mock()
        mock_text2.text = "Done. Creating Repository.java..."

        mock_write2 = Mock(spec=ToolUseBlock)
        mock_write2.name = "Write"
        mock_write2.input = {"file_path": "/path/to/Repository.java"}

        mock_message = Mock(spec=AssistantMessage)
        mock_message.content = [mock_text1, mock_write1, mock_text2, mock_write2]

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("claude_agent_sdk.query", side_effect=mock_query):
            provider = ClaudeCodeProvider()
            result = provider.generate("Create files")

            # Text should be concatenated
            assert result.response == "Creating Entity.java... Done. Creating Repository.java..."
            # Both files tracked
            assert len(result.files) == 2


class TestClaudeCodeProviderErrorHandling:
    """Tests for error handling in generate()."""

    def test_generate_wraps_sdk_exceptions(self):
        """SDK exceptions are wrapped as ProviderError."""
        async def mock_query_error(*args, **kwargs):
            raise RuntimeError("SDK connection failed")
            yield  # Make it a generator

        with patch(
            "claude_agent_sdk.query",
            side_effect=mock_query_error
        ):
            provider = ClaudeCodeProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.generate("Test prompt")

            assert "Claude Agent SDK error" in str(exc_info.value)
            assert "RuntimeError" in str(exc_info.value)
            assert "SDK connection failed" in str(exc_info.value)

    def test_generate_wraps_async_exceptions(self):
        """Async exceptions during iteration are wrapped."""
        async def mock_query_async_error(*args, **kwargs):
            yield Mock(content=[])  # First message succeeds
            raise ConnectionError("Lost connection")

        with patch(
            "claude_agent_sdk.query",
            side_effect=mock_query_async_error
        ):
            provider = ClaudeCodeProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.generate("Test prompt")

            assert "ConnectionError" in str(exc_info.value)

    def test_cli_not_found_error_has_actionable_message(self):
        """CLINotFoundError gets specific actionable message."""
        # Create a mock exception with CLINotFoundError type name
        class CLINotFoundError(Exception):
            pass

        async def mock_query_error(*args, **kwargs):
            raise CLINotFoundError("CLI not found")
            yield

        with patch("claude_agent_sdk.query", side_effect=mock_query_error):
            provider = ClaudeCodeProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.generate("Test prompt")

            assert "Claude Code CLI not found" in str(exc_info.value)
            assert "https://docs.anthropic.com/claude-code" in str(exc_info.value)

    def test_process_error_includes_details(self):
        """ProcessError includes error details."""
        class ProcessError(Exception):
            pass

        async def mock_query_error(*args, **kwargs):
            raise ProcessError("Exit code 1: Permission denied")
            yield

        with patch("claude_agent_sdk.query", side_effect=mock_query_error):
            provider = ClaudeCodeProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.generate("Test prompt")

            assert "Claude Code process failed" in str(exc_info.value)
            assert "Permission denied" in str(exc_info.value)

    def test_json_decode_error_has_actionable_message(self):
        """CLIJSONDecodeError gets specific message."""
        class CLIJSONDecodeError(Exception):
            pass

        async def mock_query_error(*args, **kwargs):
            raise CLIJSONDecodeError("Invalid JSON at position 0")
            yield

        with patch("claude_agent_sdk.query", side_effect=mock_query_error):
            provider = ClaudeCodeProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.generate("Test prompt")

            assert "Invalid response from Claude Code CLI" in str(exc_info.value)
            assert "malformed JSON" in str(exc_info.value)

    def test_timeout_error_suggests_config_increase(self):
        """TimeoutError suggests increasing max_turns or budget."""
        async def mock_query_error(*args, **kwargs):
            raise TimeoutError("Operation timed out after 600s")
            yield

        with patch("claude_agent_sdk.query", side_effect=mock_query_error):
            provider = ClaudeCodeProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.generate("Test prompt")

            assert "timed out" in str(exc_info.value)
            assert "max_turns" in str(exc_info.value)
            assert "max_budget_usd" in str(exc_info.value)

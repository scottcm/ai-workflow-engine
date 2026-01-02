"""Unit tests for GeminiCliProvider."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiwf.domain.errors import ProviderError
from aiwf.domain.models.provider_result import ProviderResult
from aiwf.domain.providers.gemini_cli_provider import (
    DEFAULT_TIMEOUT,
    FILE_WRITE_TOOLS,
    GeminiCliProvider,
    VALID_APPROVAL_MODES,
)


def make_ndjson(*events: dict) -> bytes:
    """Helper to create NDJSON byte stream."""
    lines = [json.dumps(e) for e in events]
    return "\n".join(lines).encode()


class TestGeminiCliProviderInit:
    """Tests for provider initialization."""

    def test_init_with_no_config(self):
        """Provider initializes with defaults."""
        provider = GeminiCliProvider()

        assert provider._model is None
        assert provider._sandbox is False
        assert provider._approval_mode == "yolo"
        assert provider._include_directories == []
        assert provider._allowed_tools is None
        assert provider._working_dir is None
        assert provider._timeout == DEFAULT_TIMEOUT

    def test_init_with_full_config(self):
        """Provider accepts all config keys."""
        config = {
            "model": "gemini-2.5-flash",
            "sandbox": True,
            "approval_mode": "auto_edit",
            "include_directories": ["/extra/dir"],
            "allowed_tools": ["read_file", "write_file"],
            "working_dir": "/work",
            "timeout": 300,
        }

        provider = GeminiCliProvider(config)

        assert provider._model == "gemini-2.5-flash"
        assert provider._sandbox is True
        assert provider._approval_mode == "auto_edit"
        assert provider._include_directories == ["/extra/dir"]
        assert provider._allowed_tools == ["read_file", "write_file"]
        assert provider._working_dir == "/work"
        assert provider._timeout == 300

    def test_unknown_config_keys_emit_warning(self):
        """Unknown config keys trigger UserWarning."""
        config = {
            "model": "gemini-2.5-flash",
            "unknown_key": "value",
            "another_unknown": 123,
        }

        with pytest.warns(UserWarning, match="Unknown GeminiCliProvider config keys"):
            provider = GeminiCliProvider(config)

        # Known keys still work
        assert provider._model == "gemini-2.5-flash"

    def test_invalid_timeout_raises_value_error(self):
        """timeout <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be > 0"):
            GeminiCliProvider({"timeout": 0})

        with pytest.raises(ValueError, match="timeout must be > 0"):
            GeminiCliProvider({"timeout": -100})

    def test_invalid_approval_mode_raises_value_error(self):
        """approval_mode not in valid set raises ValueError."""
        with pytest.raises(ValueError, match="approval_mode must be one of"):
            GeminiCliProvider({"approval_mode": "invalid_mode"})

    def test_include_directories_non_list_raises_value_error(self):
        """include_directories must be a list."""
        with pytest.raises(ValueError, match="include_directories must be a list"):
            GeminiCliProvider({"include_directories": "/single/path"})

    def test_allowed_tools_non_list_raises_value_error(self):
        """allowed_tools must be a list."""
        with pytest.raises(ValueError, match="allowed_tools must be a list"):
            GeminiCliProvider({"allowed_tools": "read_file"})


class TestGeminiCliProviderValidation:
    """Tests for validate() method."""

    def test_validate_passes_when_cli_available(self):
        """validate() succeeds when CLI in PATH."""
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            provider = GeminiCliProvider()
            provider.validate()  # Should not raise

    def test_validate_fails_when_cli_not_found(self):
        """validate() raises ProviderError with install link."""
        with patch("shutil.which", return_value=None):
            provider = GeminiCliProvider()

            with pytest.raises(ProviderError) as exc_info:
                provider.validate()

            assert "Gemini CLI not found" in str(exc_info.value)
            assert "github.com/google-gemini/gemini-cli" in str(exc_info.value)


class TestGeminiCliProviderBuildArgs:
    """Tests for _build_args() method."""

    def test_build_args_includes_stream_json(self):
        """Args always include -o stream-json."""
        provider = GeminiCliProvider()
        args = provider._build_args(context=None)

        assert "-o" in args
        assert "stream-json" in args

    def test_build_args_yolo_mode_adds_y_flag(self):
        """approval_mode='yolo' adds -y flag."""
        provider = GeminiCliProvider({"approval_mode": "yolo"})
        args = provider._build_args(context=None)

        assert "-y" in args

    def test_build_args_default_mode_no_flag(self):
        """approval_mode='default' adds no approval flag."""
        provider = GeminiCliProvider({"approval_mode": "default"})
        args = provider._build_args(context=None)

        assert "-y" not in args
        assert "--approval-mode" not in args

    def test_build_args_auto_edit_mode(self):
        """approval_mode='auto_edit' adds --approval-mode flag."""
        provider = GeminiCliProvider({"approval_mode": "auto_edit"})
        args = provider._build_args(context=None)

        assert "--approval-mode" in args
        idx = args.index("--approval-mode")
        assert args[idx + 1] == "auto_edit"

    def test_build_args_maps_model(self):
        """model config maps to -m flag."""
        provider = GeminiCliProvider({"model": "gemini-2.5-pro"})
        args = provider._build_args(context=None)

        assert "-m" in args
        idx = args.index("-m")
        assert args[idx + 1] == "gemini-2.5-pro"

    def test_build_args_maps_sandbox(self):
        """sandbox config maps to -s flag."""
        provider = GeminiCliProvider({"sandbox": True})
        args = provider._build_args(context=None)

        assert "-s" in args

    def test_build_args_maps_include_directories(self):
        """include_directories maps to --include-directories."""
        provider = GeminiCliProvider({
            "include_directories": ["/dir1", "/dir2"]
        })
        args = provider._build_args(context=None)

        assert args.count("--include-directories") == 2
        assert "/dir1" in args
        assert "/dir2" in args

    def test_build_args_maps_allowed_tools(self):
        """allowed_tools maps to --allowed-tools."""
        provider = GeminiCliProvider({
            "allowed_tools": ["read_file", "write_file"]
        })
        args = provider._build_args(context=None)

        assert args.count("--allowed-tools") == 2
        assert "read_file" in args
        assert "write_file" in args


class TestGeminiCliProviderNdjsonParsing:
    """Tests for _parse_ndjson_stream() method."""

    def test_parse_extracts_assistant_messages(self):
        """Parser extracts text from assistant messages."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "message", "role": "assistant", "content": "Hello world"}
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Hello world"
        assert files == {}

    def test_parse_handles_multiple_messages(self):
        """Parser concatenates multiple assistant messages."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "message", "role": "assistant", "content": "Part 1. "},
            {"type": "message", "role": "assistant", "content": "Part 2."},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Part 1. Part 2."

    def test_parse_ignores_user_messages(self):
        """Parser ignores user role messages."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "message", "role": "user", "content": "User input"},
            {"type": "message", "role": "assistant", "content": "Response"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Response"

    def test_parse_tracks_write_file_tool(self):
        """Parser tracks write_file tool calls."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "tool_use", "tool_name": "write_file", "tool_id": "t1",
             "parameters": {"file_path": "/path/to/file.txt"}},
            {"type": "tool_result", "tool_id": "t1", "status": "success"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert "/path/to/file.txt" in files
        assert files["/path/to/file.txt"] is None

    def test_parse_tracks_replace_tool(self):
        """Parser tracks replace tool calls."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "tool_use", "tool_name": "replace", "tool_id": "t1",
             "parameters": {"file_path": "/path/to/edit.txt",
                            "old_string": "old", "new_string": "new"}},
            {"type": "tool_result", "tool_id": "t1", "status": "success"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert "/path/to/edit.txt" in files

    def test_parse_tracks_multiple_file_writes(self):
        """Parser tracks multiple write operations."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "tool_use", "tool_name": "write_file", "tool_id": "t1",
             "parameters": {"file_path": "/path/file1.txt"}},
            {"type": "tool_result", "tool_id": "t1", "status": "success"},
            {"type": "tool_use", "tool_name": "replace", "tool_id": "t2",
             "parameters": {"file_path": "/path/file2.txt"}},
            {"type": "tool_result", "tool_id": "t2", "status": "success"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert len(files) == 2
        assert "/path/file1.txt" in files
        assert "/path/file2.txt" in files

    def test_parse_only_tracks_successful_writes(self):
        """Parser ignores failed tool_result events."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "tool_use", "tool_name": "write_file", "tool_id": "t1",
             "parameters": {"file_path": "/path/failed.txt"}},
            {"type": "tool_result", "tool_id": "t1", "status": "error"},
            {"type": "tool_use", "tool_name": "write_file", "tool_id": "t2",
             "parameters": {"file_path": "/path/success.txt"}},
            {"type": "tool_result", "tool_id": "t2", "status": "success"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert len(files) == 1
        assert "/path/success.txt" in files
        assert "/path/failed.txt" not in files

    def test_parse_handles_malformed_json(self):
        """Parser logs warning with sample content and continues."""
        provider = GeminiCliProvider()
        # Mix valid and invalid JSON lines
        stdout = b'{"type":"message","role":"assistant","content":"Valid"}\n'
        stdout += b'not valid json\n'
        stdout += b'{"type":"message","role":"assistant","content":" end"}\n'

        with patch.object(provider, "_parse_ndjson_stream", wraps=provider._parse_ndjson_stream):
            response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Valid end"

    def test_parse_handles_partial_line(self):
        """Parser handles truncated/incomplete JSON lines gracefully."""
        provider = GeminiCliProvider()
        stdout = b'{"type":"message","role":"assistant","content":"Complete"}\n'
        stdout += b'{"type":"message","role":"assis'  # Truncated

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Complete"

    def test_parse_handles_empty_output(self):
        """Parser returns empty response for empty output."""
        provider = GeminiCliProvider()
        stdout = b""

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == ""
        assert files == {}

    def test_parse_handles_blank_lines(self):
        """Parser skips blank lines."""
        provider = GeminiCliProvider()
        stdout = b'\n\n{"type":"message","role":"assistant","content":"Hello"}\n\n'

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Hello"

    def test_parse_handles_mixed_events(self):
        """Parser handles interleaved message and tool events."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "init", "session_id": "abc123", "model": "gemini-2.5"},
            {"type": "message", "role": "assistant", "content": "Creating file..."},
            {"type": "tool_use", "tool_name": "write_file", "tool_id": "t1",
             "parameters": {"file_path": "/path/file.txt"}},
            {"type": "tool_result", "tool_id": "t1", "status": "success"},
            {"type": "message", "role": "assistant", "content": " Done!"},
            {"type": "result", "status": "success"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert response == "Creating file... Done!"
        assert "/path/file.txt" in files

    def test_parse_ignores_read_file_tool(self):
        """Parser does not track read_file tool calls."""
        provider = GeminiCliProvider()
        stdout = make_ndjson(
            {"type": "tool_use", "tool_name": "read_file", "tool_id": "t1",
             "parameters": {"file_path": "/path/read.txt"}},
            {"type": "tool_result", "tool_id": "t1", "status": "success"},
        )

        response, files = provider._parse_ndjson_stream(stdout)

        assert files == {}


class TestGeminiCliProviderGenerate:
    """Tests for generate() method with mocked subprocess."""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock asyncio.create_subprocess_exec."""
        with patch("asyncio.create_subprocess_exec") as mock:
            process = AsyncMock()
            process.returncode = 0
            process.communicate = AsyncMock(return_value=(
                make_ndjson(
                    {"type": "message", "role": "assistant", "content": "Hello"}
                ),
                b"",
            ))
            mock.return_value = process
            yield mock, process

    def test_generate_passes_prompt_via_flag(self, mock_subprocess):
        """generate() passes prompt via -p flag."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider()
        result = provider.generate("Test prompt")

        # Verify -p flag with prompt content in args
        call_args = mock.call_args[0]
        assert "-p" in call_args
        p_index = call_args.index("-p")
        assert call_args[p_index + 1] == "Test prompt"

    def test_generate_directs_gemini_to_read_prompt_file(self, mock_subprocess):
        """generate() tells Gemini to read the prompt file itself."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider()
        result = provider.generate(
            prompt="ignored",
            context={"prompt_file": "/path/to/prompt.md"},
        )

        # Verify -p flag tells Gemini to process the file
        call_args = mock.call_args[0]
        assert "-p" in call_args
        p_index = call_args.index("-p")
        assert "Process the prompt in /path/to/prompt.md" in call_args[p_index + 1]

    def test_generate_uses_file_reference_over_direct_prompt(self, mock_subprocess):
        """File reference is used when prompt_file is in context."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider()
        result = provider.generate(
            prompt="This should be ignored",
            context={"prompt_file": "/path/to/prompt.md"},
        )

        # Verify file reference is passed, not direct prompt
        call_args = mock.call_args[0]
        p_index = call_args.index("-p")
        assert "/path/to/prompt.md" in call_args[p_index + 1]
        assert "This should be ignored" not in call_args[p_index + 1]

    def test_generate_returns_response_text(self, mock_subprocess):
        """generate() returns parsed response text."""
        mock, process = mock_subprocess
        process.communicate.return_value = (
            make_ndjson(
                {"type": "message", "role": "assistant", "content": "Response text"}
            ),
            b"",
        )

        provider = GeminiCliProvider()
        result = provider.generate("Test")

        assert isinstance(result, ProviderResult)
        assert result.response == "Response text"

    def test_generate_returns_files_written(self, mock_subprocess):
        """generate() returns tracked files in ProviderResult."""
        mock, process = mock_subprocess
        process.communicate.return_value = (
            make_ndjson(
                {"type": "message", "role": "assistant", "content": "Created file"},
                {"type": "tool_use", "tool_name": "write_file", "tool_id": "t1",
                 "parameters": {"file_path": "/path/new.txt"}},
                {"type": "tool_result", "tool_id": "t1", "status": "success"},
            ),
            b"",
        )

        provider = GeminiCliProvider()
        result = provider.generate("Create a file")

        assert "/path/new.txt" in result.files
        assert result.files["/path/new.txt"] is None

    def test_generate_with_system_prompt(self, mock_subprocess):
        """generate() prepends system prompt to prompt via -p flag."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider()
        result = provider.generate(
            prompt="User prompt",
            system_prompt="System instructions",
        )

        # Verify combined prompt was passed via -p flag
        call_args = mock.call_args[0]
        p_index = call_args.index("-p")
        combined_prompt = call_args[p_index + 1]
        assert "System instructions" in combined_prompt
        assert "User prompt" in combined_prompt
        assert combined_prompt.index("System instructions") < combined_prompt.index("User prompt")

    def test_generate_uses_config_timeout(self, mock_subprocess):
        """generate() uses configured timeout value."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider({"timeout": 120})

        # Track the timeout passed to wait_for
        captured_timeout = None

        async def capturing_wait_for(coro, *, timeout=None):
            """Wrapper that captures timeout and executes the coroutine."""
            nonlocal captured_timeout
            captured_timeout = timeout
            return await coro

        with patch(
            "aiwf.domain.providers.gemini_cli_provider.asyncio.wait_for",
            side_effect=capturing_wait_for,
        ):
            provider.generate("Test", None, None)

        assert captured_timeout == 120

    def test_generate_uses_context_project_root_as_cwd(self, mock_subprocess):
        """generate() uses project_root as working directory."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider()
        result = provider.generate(
            prompt="Test",
            context={"project_root": "/my/project"},
        )

        # Verify cwd was passed to subprocess
        call_kwargs = mock.call_args[1]
        assert call_kwargs["cwd"] == "/my/project"

    def test_generate_prefers_config_working_dir(self, mock_subprocess):
        """Config working_dir takes precedence over context."""
        mock, process = mock_subprocess

        provider = GeminiCliProvider({"working_dir": "/config/dir"})
        result = provider.generate(
            prompt="Test",
            context={"project_root": "/context/dir"},
        )

        call_kwargs = mock.call_args[1]
        assert call_kwargs["cwd"] == "/config/dir"


class TestGeminiCliProviderErrorHandling:
    """Tests for error handling in generate()."""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock asyncio.create_subprocess_exec."""
        with patch("asyncio.create_subprocess_exec") as mock:
            process = AsyncMock()
            process.returncode = 0
            process.communicate = AsyncMock(return_value=(b"", b""))
            mock.return_value = process
            yield mock, process

    def test_timeout_raises_provider_error(self, mock_subprocess):
        """Timeout raises ProviderError with suggestion."""
        mock, process = mock_subprocess
        process.communicate.side_effect = asyncio.TimeoutError()
        process.kill = MagicMock()

        provider = GeminiCliProvider({"timeout": 10})

        with pytest.raises(ProviderError) as exc_info:
            provider.generate("Test")

        assert "timed out" in str(exc_info.value)
        assert "10s" in str(exc_info.value)
        process.kill.assert_called_once()

    def test_process_error_raises_provider_error(self, mock_subprocess):
        """Non-zero exit code raises ProviderError."""
        mock, process = mock_subprocess
        process.returncode = 1
        process.communicate.return_value = (b"", b"Some error message")

        provider = GeminiCliProvider()

        with pytest.raises(ProviderError) as exc_info:
            provider.generate("Test")

        assert "exit 1" in str(exc_info.value)
        assert "Some error message" in str(exc_info.value)

    def test_auth_error_suggests_login(self, mock_subprocess):
        """Auth errors suggest gemini auth login."""
        mock, process = mock_subprocess
        process.returncode = 1
        process.communicate.return_value = (b"", b"Authentication failed: not logged in")

        provider = GeminiCliProvider()

        with pytest.raises(ProviderError) as exc_info:
            provider.generate("Test")

        assert "authentication error" in str(exc_info.value).lower()
        assert "gemini auth login" in str(exc_info.value)

    def test_cli_not_found_has_install_link(self, mock_subprocess):
        """FileNotFoundError includes install link."""
        mock, process = mock_subprocess
        mock.side_effect = FileNotFoundError("gemini not found")

        provider = GeminiCliProvider()

        with pytest.raises(ProviderError) as exc_info:
            provider.generate("Test")

        assert "Gemini CLI not found" in str(exc_info.value)
        assert "github.com/google-gemini/gemini-cli" in str(exc_info.value)

    def test_exit_code_127_suggests_install(self, mock_subprocess):
        """Exit code 127 (command not found) includes install link."""
        mock, process = mock_subprocess
        process.returncode = 127
        process.communicate.return_value = (b"", b"gemini: command not found")

        provider = GeminiCliProvider()

        with pytest.raises(ProviderError) as exc_info:
            provider.generate("Test")

        assert "Gemini CLI not found" in str(exc_info.value)


class TestGeminiCliProviderMetadata:
    """Tests for get_metadata() class method."""

    def test_metadata_has_correct_name(self):
        """Metadata name is 'gemini-cli'."""
        metadata = GeminiCliProvider.get_metadata()
        assert metadata["name"] == "gemini-cli"

    def test_metadata_has_all_config_keys(self):
        """Metadata lists all supported config keys."""
        metadata = GeminiCliProvider.get_metadata()
        expected_keys = {
            "model",
            "sandbox",
            "approval_mode",
            "include_directories",
            "allowed_tools",
            "working_dir",
            "timeout",
        }
        assert set(metadata["config_keys"]) == expected_keys

    def test_metadata_fs_ability_is_local_write(self):
        """fs_ability indicates local file write capability."""
        metadata = GeminiCliProvider.get_metadata()
        assert metadata["fs_ability"] == "local-write"

    def test_metadata_has_default_timeout(self):
        """Metadata includes default timeout."""
        metadata = GeminiCliProvider.get_metadata()
        assert metadata["default_response_timeout"] == DEFAULT_TIMEOUT

    def test_metadata_requires_config_is_false(self):
        """Provider does not require config."""
        metadata = GeminiCliProvider.get_metadata()
        assert metadata["requires_config"] is False


class TestGeminiCliProviderConstants:
    """Tests for module-level constants."""

    def test_file_write_tools_contains_both_tools(self):
        """FILE_WRITE_TOOLS includes write_file and replace."""
        assert "write_file" in FILE_WRITE_TOOLS
        assert "replace" in FILE_WRITE_TOOLS
        assert len(FILE_WRITE_TOOLS) == 2

    def test_valid_approval_modes(self):
        """VALID_APPROVAL_MODES contains expected values."""
        assert "default" in VALID_APPROVAL_MODES
        assert "auto_edit" in VALID_APPROVAL_MODES
        assert "yolo" in VALID_APPROVAL_MODES
        assert len(VALID_APPROVAL_MODES) == 3

    def test_default_timeout_is_reasonable(self):
        """Default timeout is 10 minutes."""
        assert DEFAULT_TIMEOUT == 600

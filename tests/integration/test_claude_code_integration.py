"""Integration tests for ClaudeCodeAIProvider.

These tests invoke the actual Claude Code CLI via the Agent SDK and require:
1. Claude Code CLI installed (`claude` command available)
2. Valid Claude authentication configured (via `claude login`)

Tests are marked with @pytest.mark.integration and @pytest.mark.claude_code
so they can be skipped in CI environments without Claude CLI.

Run with: pytest tests/integration/test_claude_code_integration.py -v
Skip with: pytest -m "not claude_code"
"""

import shutil
from pathlib import Path

import pytest

from aiwf.domain.errors import ProviderError
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.domain.providers.claude_code_provider import ClaudeCodeAIProvider


# Check if Claude CLI is available
def claude_cli_available() -> bool:
    """Check if claude CLI is available in PATH."""
    return shutil.which("claude") is not None


# Custom markers
pytestmark = [
    pytest.mark.integration,
    pytest.mark.claude_code,
]


@pytest.fixture
def provider():
    """Create a ClaudeCodeAIProvider instance."""
    return ClaudeCodeAIProvider()


@pytest.fixture
def provider_with_read_only():
    """Create a ClaudeCodeAIProvider with read-only tools."""
    return ClaudeCodeAIProvider({
        "allowed_tools": ["Read", "Grep", "Glob"],
        "permission_mode": "plan",
    })


class TestClaudeCodeValidation:
    """Integration tests for validate() method."""

    @pytest.mark.skipif(
        not claude_cli_available(),
        reason="Claude CLI not installed"
    )
    def test_validate_succeeds(self, provider):
        """validate() succeeds when Claude CLI is installed."""
        provider.validate()  # Should not raise

    @pytest.mark.skipif(
        claude_cli_available(),
        reason="Test only valid when Claude CLI is NOT installed"
    )
    def test_validate_fails_without_cli(self, provider):
        """validate() raises when Claude CLI is not installed."""
        with pytest.raises(ProviderError):
            provider.validate()


@pytest.mark.skipif(
    not claude_cli_available(),
    reason="Claude CLI not installed"
)
class TestClaudeCodeGenerate:
    """Integration tests for generate() method.

    These tests make real calls to Claude and may incur costs/usage.
    They are designed to be fast with minimal prompts.
    """

    def test_simple_prompt(self, provider_with_read_only):
        """Provider can generate a simple response."""
        result = provider_with_read_only.generate(
            "Respond with exactly the word 'HELLO' and nothing else.",
        )

        assert isinstance(result, AIProviderResult)
        assert result.response is not None
        assert "HELLO" in result.response.upper()

    def test_with_system_prompt(self, provider_with_read_only):
        """Provider respects system prompt."""
        result = provider_with_read_only.generate(
            "What is 2+2?",
            system_prompt="Respond with only the numeric answer, no explanation.",
        )

        assert isinstance(result, AIProviderResult)
        assert result.response is not None
        assert "4" in result.response

    def test_with_context(self, provider_with_read_only, tmp_path):
        """Provider can use context directories."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("The secret word is BANANA.")

        context = {
            "project_root": str(tmp_path),
        }

        result = provider_with_read_only.generate(
            f"Read the file at {test_file} and tell me the secret word. "
            "Respond with just the secret word.",
            context=context,
        )

        assert isinstance(result, AIProviderResult)
        assert result.response is not None
        assert "BANANA" in result.response.upper()

    def test_handles_complex_prompt(self, provider_with_read_only):
        """Provider handles multi-line prompts."""
        prompt = """
        I have a task with multiple requirements:
        1. Count to three
        2. Say each number on a new line
        3. End with "DONE"

        Execute this task now.
        """

        result = provider_with_read_only.generate(prompt)

        assert isinstance(result, AIProviderResult)
        assert result.response is not None
        # Should contain numbers and DONE
        assert "1" in result.response
        assert "DONE" in result.response.upper()


@pytest.mark.skipif(
    not claude_cli_available(),
    reason="Claude CLI not installed"
)
class TestClaudeCodeFileWrite:
    """Integration tests for file writing capability."""

    def test_file_write_tracked_in_result(self, tmp_path):
        """File writes are tracked in AIProviderResult.files."""
        provider = ClaudeCodeAIProvider({
            "working_dir": str(tmp_path),
            "allowed_tools": ["Read", "Write"],
            "permission_mode": "acceptEdits",
        })

        result = provider.generate(
            f"Create a file called 'test_output.txt' in {tmp_path} "
            "containing the text 'Hello from Claude'."
        )

        assert isinstance(result, AIProviderResult)
        # Verify file was created
        test_file = tmp_path / "test_output.txt"
        assert test_file.exists(), "File should have been created"

        # Verify file was tracked (path ends with test_output.txt)
        tracked_files = list(result.files.keys())
        assert any("test_output.txt" in f for f in tracked_files), (
            f"File should be tracked. Found: {tracked_files}"
        )


@pytest.mark.skipif(
    not claude_cli_available(),
    reason="Claude CLI not installed"
)
class TestClaudeCodeAIProviderModels:
    """Integration tests for model selection."""

    def test_default_model(self):
        """Provider works with default model."""
        provider = ClaudeCodeAIProvider({
            "allowed_tools": ["Read"],  # Minimal tools
            "permission_mode": "plan",
        })

        result = provider.generate("Say 'test'")

        assert isinstance(result, AIProviderResult)
        assert result.response is not None

    def test_specific_model(self):
        """Provider can use specific model."""
        provider = ClaudeCodeAIProvider({
            "model": "sonnet",
            "allowed_tools": ["Read"],
            "permission_mode": "plan",
        })

        result = provider.generate("Say 'sonnet test'")

        assert isinstance(result, AIProviderResult)
        assert result.response is not None


@pytest.mark.skipif(
    not claude_cli_available(),
    reason="Claude CLI not installed"
)
class TestClaudeCodeAIProviderConfig:
    """Integration tests for configuration options."""

    def test_max_turns_limits_iterations(self):
        """max_turns config limits agent iterations."""
        provider = ClaudeCodeAIProvider({
            "max_turns": 1,
            "allowed_tools": ["Read"],
            "permission_mode": "plan",
        })

        # This should complete quickly due to max_turns=1
        result = provider.generate("Explain what max_turns does briefly.")

        assert isinstance(result, AIProviderResult)
        # With max_turns=1, we may get partial response but should not error

    def test_thinking_tokens_config(self):
        """max_thinking_tokens config is accepted."""
        provider = ClaudeCodeAIProvider({
            "max_thinking_tokens": 0,  # Disable thinking
            "allowed_tools": ["Read"],
            "permission_mode": "plan",
        })

        result = provider.generate("Say 'test'")

        assert isinstance(result, AIProviderResult)


@pytest.mark.skipif(
    not claude_cli_available(),
    reason="Claude CLI not installed"
)
class TestClaudeCodeAIProviderErrors:
    """Integration tests for error handling."""

    def test_invalid_permission_mode_fails(self):
        """Provider fails with invalid permission mode."""
        provider = ClaudeCodeAIProvider({
            "permission_mode": "invalid_mode",
        })

        # This should fail when Claude rejects the invalid mode
        with pytest.raises(ProviderError):
            provider.generate("Say 'test'")


class TestClaudeCodeAIProviderMetadataIntegration:
    """Integration tests for provider metadata."""

    def test_metadata_is_complete(self):
        """Provider metadata has all required fields."""
        metadata = ClaudeCodeAIProvider.get_metadata()

        required_fields = [
            "name",
            "description",
            "requires_config",
            "config_keys",
            "default_connection_timeout",
            "default_response_timeout",
            "fs_ability",
            "supports_system_prompt",
        ]

        for field in required_fields:
            assert field in metadata, f"Missing metadata field: {field}"

    def test_metadata_values_reasonable(self):
        """Provider metadata has reasonable values."""
        metadata = ClaudeCodeAIProvider.get_metadata()

        assert metadata["name"] == "claude-code"
        assert metadata["default_response_timeout"] >= 60
        assert metadata["supports_system_prompt"] is True

"""Integration tests for GeminiCliProvider.

These tests require the Gemini CLI to be installed and authenticated.
They are skipped if the CLI is not available.
"""

import shutil

import pytest

from aiwf.domain.errors import ProviderError
from aiwf.domain.providers.gemini_cli_provider import GeminiCliProvider

# Check if Gemini CLI is available
GEMINI_AVAILABLE = shutil.which("gemini") is not None


@pytest.mark.skipif(not GEMINI_AVAILABLE, reason="Gemini CLI not installed")
@pytest.mark.gemini_cli
class TestGeminiCliIntegration:
    """Integration tests requiring real Gemini CLI."""

    def test_simple_prompt_returns_response(self):
        """Basic prompt gets a response."""
        provider = GeminiCliProvider({"timeout": 60})
        provider.validate()
        result = provider.generate("Say 'hello' and nothing else.")

        assert result.response is not None
        assert len(result.response) > 0
        # Response should contain "hello" in some form
        assert "hello" in result.response.lower()

    def test_file_write_tracked_in_result(self, tmp_path):
        """File writes appear in ProviderResult.files."""
        provider = GeminiCliProvider({
            "working_dir": str(tmp_path),
            "approval_mode": "yolo",
            "timeout": 120,
        })
        provider.validate()

        result = provider.generate(
            "Create a file called test_output.txt containing only the text 'test content'. "
            "Do not include any other text or explanation."
        )

        # Verify file was written
        test_file = tmp_path / "test_output.txt"
        assert test_file.exists(), f"Expected file at {test_file}"

        # Verify tracked in result
        assert len(result.files) > 0
        assert any("test_output.txt" in f for f in result.files.keys())

    def test_file_edit_tracked_via_replace(self, tmp_path):
        """File edits via replace tool appear in ProviderResult.files."""
        # Create initial file
        test_file = tmp_path / "edit_me.txt"
        test_file.write_text("old content here")

        provider = GeminiCliProvider({
            "working_dir": str(tmp_path),
            "approval_mode": "yolo",
            "timeout": 120,
        })
        provider.validate()

        result = provider.generate(
            "Edit edit_me.txt to change 'old' to 'new'. Only make this change."
        )

        # Verify file was modified
        content = test_file.read_text()
        assert "new content" in content or "new" in content

        # Verify tracked in result
        assert any("edit_me.txt" in f for f in result.files.keys())

    def test_model_config_applied(self):
        """Model config is passed to CLI."""
        provider = GeminiCliProvider({
            "model": "gemini-2.5-flash",
            "timeout": 60,
        })
        provider.validate()

        result = provider.generate("Say 'model test' and nothing else.")
        assert result.response is not None

    def test_timeout_config_works(self):
        """timeout config limits execution time."""
        provider = GeminiCliProvider({"timeout": 1})  # 1 second
        provider.validate()

        # Very short timeout should fail on any real prompt
        with pytest.raises(ProviderError, match="timed out"):
            provider.generate(
                "Write a very long essay about the history of computing, "
                "including detailed analysis of each decade from 1950 to 2020."
            )

    def test_file_based_prompt(self, tmp_path):
        """File-based prompt delivery works via context['prompt_file']."""
        # Write prompt to file
        prompt_file = tmp_path / "test-prompt.md"
        prompt_file.write_text("Say 'file prompt works' and nothing else.")

        provider = GeminiCliProvider({
            "working_dir": str(tmp_path),
            "approval_mode": "yolo",
            "timeout": 60,
        })
        provider.validate()

        result = provider.generate(
            prompt="This text should be ignored when file is provided",
            context={"prompt_file": str(prompt_file)},
        )

        assert result.response is not None
        assert "file prompt works" in result.response.lower()

    def test_sandbox_mode(self, tmp_path):
        """Sandbox mode can be enabled."""
        provider = GeminiCliProvider({
            "sandbox": True,
            "working_dir": str(tmp_path),
            "timeout": 60,
        })
        provider.validate()

        result = provider.generate("Say 'sandbox test' and nothing else.")
        assert result.response is not None

    def test_empty_response_handling(self):
        """Empty or minimal responses are handled gracefully."""
        provider = GeminiCliProvider({"timeout": 60})
        provider.validate()

        # Even if response is minimal, should not crash
        result = provider.generate("Respond with only: ok")
        assert result is not None
        assert isinstance(result.response, str)

    def test_multiple_file_operations(self, tmp_path):
        """Multiple file operations in one session are tracked."""
        provider = GeminiCliProvider({
            "working_dir": str(tmp_path),
            "approval_mode": "yolo",
            "timeout": 180,
        })
        provider.validate()

        result = provider.generate(
            "Create two files: file1.txt containing 'content 1' and "
            "file2.txt containing 'content 2'. No other text."
        )

        # Both files should exist
        assert (tmp_path / "file1.txt").exists()
        assert (tmp_path / "file2.txt").exists()

        # Both should be tracked
        assert len(result.files) >= 2

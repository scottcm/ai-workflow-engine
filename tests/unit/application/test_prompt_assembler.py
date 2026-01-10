# tests/unit/application/test_prompt_assembler.py
"""Tests for PromptAssembler - engine variable substitution and output instructions."""

from pathlib import Path

import pytest

from aiwf.application.prompt_assembler import PromptAssembler
from aiwf.domain.models.workflow_state import (
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)


@pytest.fixture
def base_state() -> WorkflowState:
    """Create base workflow state for testing."""
    return WorkflowState(
        session_id="test-session",
        profile="jpa-mt",
        phase=WorkflowPhase.PLAN,
        stage=WorkflowStage.PROMPT,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=1,
        standards_hash="abc123",
        ai_providers={"planner": "manual", "generator": "manual"},
        metadata={},
    )


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Create session directory."""
    session = tmp_path / "sessions" / "test-session"
    session.mkdir(parents=True)
    return session


class TestSubstituteEngineVariables:
    """Tests for engine variable substitution."""

    def test_substitutes_standards_variable(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify {{STANDARDS}} is replaced with standards-bundle.md path."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Read standards from {{STANDARDS}}"

        result = assembler.assemble(profile_prompt, fs_ability="none")

        expected_path = str(session_dir / "standards-bundle.md")
        assert expected_path in result["user_prompt"]
        assert "{{STANDARDS}}" not in result["user_prompt"]

    def test_substitutes_plan_variable(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify {{PLAN}} is replaced with plan.md path."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Follow the plan at {{PLAN}}"

        result = assembler.assemble(profile_prompt, fs_ability="none")

        expected_path = str(session_dir / "plan.md")
        assert expected_path in result["user_prompt"]
        assert "{{PLAN}}" not in result["user_prompt"]

    def test_substitutes_multiple_variables(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify multiple variables are all substituted."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Standards: {{STANDARDS}}\nPlan: {{PLAN}}"

        result = assembler.assemble(profile_prompt, fs_ability="none")

        assert "{{STANDARDS}}" not in result["user_prompt"]
        assert "{{PLAN}}" not in result["user_prompt"]
        assert str(session_dir / "standards-bundle.md") in result["user_prompt"]
        assert str(session_dir / "plan.md") in result["user_prompt"]


class TestOutputInstructions:
    """Tests for output instruction generation based on fs_ability."""

    def test_local_write_includes_full_path(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify local-write fs_ability uses full path."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Generate code"
        response_relpath = "iteration-1/generation-response.md"

        result = assembler.assemble(
            profile_prompt,
            fs_ability="local-write",
            response_relpath=response_relpath,
        )

        # Should include "Save your response to" with full path
        assert "Save your response to" in result["user_prompt"]
        expected_path = str(session_dir / response_relpath)
        assert expected_path in result["user_prompt"]

    def test_local_read_uses_filename_only(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify local-read fs_ability uses filename only."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Generate code"
        response_relpath = "iteration-1/generation-response.md"

        result = assembler.assemble(
            profile_prompt,
            fs_ability="local-read",
            response_relpath=response_relpath,
        )

        # Should include "Name your output file" with filename only
        assert "Name your output file" in result["user_prompt"]
        assert "generation-response.md" in result["user_prompt"]

    def test_write_only_creates_downloadable(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify write-only fs_ability uses downloadable file instruction."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Generate code"
        response_relpath = "iteration-1/generation-response.md"

        result = assembler.assemble(
            profile_prompt,
            fs_ability="write-only",
            response_relpath=response_relpath,
        )

        # Should include "Create a downloadable file"
        assert "Create a downloadable file" in result["user_prompt"]
        assert "generation-response.md" in result["user_prompt"]

    def test_none_adds_no_instructions(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify none fs_ability adds no output instructions."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Generate code"
        response_relpath = "iteration-1/generation-response.md"

        result = assembler.assemble(
            profile_prompt,
            fs_ability="none",
            response_relpath=response_relpath,
        )

        # Should not have output instructions
        assert "Save your response" not in result["user_prompt"]
        assert "Name your output" not in result["user_prompt"]
        assert "Create a downloadable" not in result["user_prompt"]
        # Original prompt should be there
        assert "Generate code" in result["user_prompt"]

    def test_no_response_path_adds_no_instructions(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify missing response_relpath adds no output instructions."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Generate code"

        result = assembler.assemble(
            profile_prompt,
            fs_ability="local-write",
            response_relpath=None,
        )

        # Should not have output instructions when no response path
        assert "Save your response" not in result["user_prompt"]
        assert "Output Destination" not in result["user_prompt"]


class TestAssemble:
    """Tests for the overall assemble method."""

    def test_returns_dict_with_required_keys(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify assemble returns dict with user_prompt and system_prompt."""
        assembler = PromptAssembler(session_dir, base_state)

        result = assembler.assemble("Test prompt", fs_ability="none")

        assert "user_prompt" in result
        assert "system_prompt" in result
        assert result["system_prompt"] == ""  # Reserved for future use

    def test_concatenates_with_separator(
        self, base_state: WorkflowState, session_dir: Path
    ):
        """Verify prompt and output instructions are separated correctly."""
        assembler = PromptAssembler(session_dir, base_state)
        profile_prompt = "Generate code"

        result = assembler.assemble(
            profile_prompt,
            fs_ability="local-write",
            response_relpath="iteration-1/test.md",
        )

        # Should have separator between prompt and instructions
        assert "\n\n---\n\n" in result["user_prompt"]
        # Profile prompt should come first
        assert result["user_prompt"].startswith("Generate code")

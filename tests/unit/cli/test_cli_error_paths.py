"""Tests for CLI error paths that were previously uncovered.

Covers:
- init exception in plain text mode raises ClickException
- step exception in JSON mode emits proper error JSON
- approve with ERROR status in JSON mode emits error output
- approve with ERROR status in plain text mode exits with code 1
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from aiwf.interface.cli.cli import cli
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus


def _state(*, phase, status, iteration, last_error=None, plan_approved=False, review_approved=False, artifacts=None, prompt_hashes=None, plan_hash=None, review_hash=None):
    """Create a mock state object for testing."""
    class _S:
        pass

    s = _S()
    s.phase = phase
    s.status = status
    s.current_iteration = iteration
    s.last_error = last_error
    s.plan_approved = plan_approved
    s.review_approved = review_approved
    s.artifacts = artifacts or []
    s.prompt_hashes = prompt_hashes or {}
    s.plan_hash = plan_hash
    s.review_hash = review_hash
    return s


def test_init_exception_plain_text_raises_click_exception(monkeypatch):
    """In plain text mode, init exception raises ClickException (exit 1, error in output)."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_initialize_run(self, **kwargs):
        raise ValueError("Profile validation failed: missing required field")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(
            cli,
            [
                "init",
                "--scope", "domain",
                "--entity", "Foo",
                "--table", "foo",
                "--bounded-context", "bc",
            ],
            prog_name="aiwf",
        )

    assert result.exit_code == 1
    # Error message should be in output
    assert "Profile validation failed" in result.output or "missing required field" in result.output


def test_init_exception_json_mode_emits_error_output(monkeypatch):
    """In JSON mode, init exception emits proper error JSON."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_initialize_run(self, **kwargs):
        raise ValueError("Invalid scope: foobar")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Foo",
                "--table", "foo",
                "--bounded-context", "bc",
            ],
            prog_name="aiwf",
        )

    assert result.exit_code == 1
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "init"
    assert obj["exit_code"] == 1
    assert "error" in obj
    assert "Invalid scope" in obj["error"]


def test_step_exception_json_mode_emits_error_output(monkeypatch):
    """In JSON mode, step exception emits proper error JSON with all required fields."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_step(self, session_id: str):
        raise RuntimeError("Session corrupted: invalid phase history")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["--json", "step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "step"
    assert obj["exit_code"] == 1
    assert obj["session_id"] == "sess_123"
    assert "error" in obj
    assert "Session corrupted" in obj["error"]
    # These fields are present on error (empty strings, not omitted)
    assert obj["phase"] == ""
    assert obj["status"] == ""
    # iteration is None and excluded via exclude_none=True in model_dump_json
    assert obj.get("iteration") is None
    assert obj["noop_awaiting_artifact"] is False
    assert obj["awaiting_paths"] == []


def test_approve_error_status_json_emits_error_output(monkeypatch):
    """When approve returns ERROR status in JSON mode, emits proper error JSON."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        return _state(
            phase=WorkflowPhase.GENERATING,
            status=WorkflowStatus.ERROR,
            iteration=1,
            last_error="Cannot approve: missing prompt file 'iteration-1/generation-prompt.md'",
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["--json", "approve", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "approve"
    assert obj["exit_code"] == 1
    assert obj["session_id"] == "sess_123"
    assert obj["phase"] == "GENERATING"
    assert obj["status"] == "ERROR"
    assert obj["approved"] is False
    assert "error" in obj
    assert "missing prompt file" in obj["error"]


def test_approve_error_status_plain_exits_1(monkeypatch):
    """When approve returns ERROR status in plain text mode, exits with code 1."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        return _state(
            phase=WorkflowPhase.GENERATING,
            status=WorkflowStatus.ERROR,
            iteration=1,
            last_error="Cannot approve: provider connection failed",
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["approve", "sess_123"], prog_name="aiwf")

    # Plain text mode with ERROR status should exit 1
    assert result.exit_code == 1


def test_approve_exception_json_mode_emits_error_output(monkeypatch):
    """When approve raises exception in JSON mode, emits proper error JSON."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        raise RuntimeError("Unexpected filesystem error")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["--json", "approve", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "approve"
    assert obj["exit_code"] == 1
    assert obj["session_id"] == "sess_123"
    assert "error" in obj
    assert "Unexpected filesystem error" in obj["error"]
    assert obj["approved"] is False


def test_approve_exception_plain_text_exits_1_with_message(monkeypatch):
    """When approve raises exception in plain text mode, exits 1 with error message."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        raise RuntimeError("Permission denied: cannot write to session directory")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["approve", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    # Error message should be visible
    assert "Permission denied" in result.output or "Cannot approve" in result.output


def test_approve_success_json_emits_proper_output(monkeypatch):
    """Verify successful approve in JSON mode works correctly (regression guard)."""
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.interface.cli.cli as cli_mod

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        return _state(
            phase=WorkflowPhase.PLANNED,
            status=WorkflowStatus.IN_PROGRESS,
            iteration=1,
            plan_approved=True,
            plan_hash="abc123def456",
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["--json", "approve", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "approve"
    assert obj["exit_code"] == 0
    assert obj["session_id"] == "sess_123"
    assert obj["phase"] == "PLANNED"
    assert obj["status"] == "IN_PROGRESS"
    assert obj["approved"] is True
    assert "plan.md" in obj["hashes"]

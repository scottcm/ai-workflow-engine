from pathlib import Path
import pytest
from click.testing import CliRunner

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState, WorkflowStatus, ExecutionMode, PhaseTransition


def _fake_state(session_id: str) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        profile="test-profile",
        scope="test-scope",
        entity="TestEntity",
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=WorkflowPhase.PLANNED,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=1,
        standards_hash="0" * 64,
        phase_history=[PhaseTransition(phase=WorkflowPhase.PLANNED, status=WorkflowStatus.IN_PROGRESS)],
    )


def test_cli_approve_invokes_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Import CLI module and patch sessions root
    import aiwf.interface.cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", tmp_path, raising=True)

    # Import click group
    from aiwf.interface.cli.cli import cli

    calls = {}

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        calls["session_id"] = session_id
        calls["hash_prompts"] = hash_prompts
        return _fake_state(session_id)

    import aiwf.application.workflow_orchestrator as orch_mod
    monkeypatch.setattr(orch_mod.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["approve", "abc123"])

    assert result.exit_code == 0
    assert calls["session_id"] == "abc123"
    assert calls["hash_prompts"] is False


def test_cli_approve_hash_prompts_flags_override_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import aiwf.interface.cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", tmp_path, raising=True)

    from aiwf.interface.cli.cli import cli

    calls = {}

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        calls["session_id"] = session_id
        calls["hash_prompts"] = hash_prompts
        return _fake_state(session_id)

    import aiwf.application.workflow_orchestrator as orch_mod
    monkeypatch.setattr(orch_mod.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    # config says hash_prompts False, CLI overrides True
    import aiwf.application.config_loader as cfg_mod
    monkeypatch.setattr(cfg_mod, "load_config", lambda project_root, user_home: {"hash_prompts": False, "profile": "x", "providers": {}, "dev": None}, raising=True)

    runner = CliRunner()
    r1 = runner.invoke(cli, ["approve", "--hash-prompts", "id1"])
    assert r1.exit_code == 0
    assert calls["hash_prompts"] is True

    # config says hash_prompts True, CLI overrides False
    monkeypatch.setattr(cfg_mod, "load_config", lambda project_root, user_home: {"hash_prompts": True, "profile": "x", "providers": {}, "dev": None}, raising=True)

    r2 = runner.invoke(cli, ["approve", "--no-hash-prompts", "id2"])
    assert r2.exit_code == 0
    assert calls["hash_prompts"] is False


def test_cli_approve_missing_inputs_exits_nonzero_and_prints_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import aiwf.interface.cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", tmp_path, raising=True)

    from aiwf.interface.cli.cli import cli

    def fake_approve(self, session_id: str, hash_prompts: bool = False):
        raise FileNotFoundError("Cannot approve: missing prompt file 'iteration-1/generation-prompt.md' (expected at X)")

    import aiwf.application.workflow_orchestrator as orch_mod
    monkeypatch.setattr(orch_mod.WorkflowOrchestrator, "approve", fake_approve, raising=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["approve", "missing"])

    assert result.exit_code != 0
    assert "Cannot approve: missing" in result.output

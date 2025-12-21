import json
from pathlib import Path
from click.testing import CliRunner

from aiwf.cli import cli
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus


def _norm(p: str) -> str:
    # Normalize backslashes to forward slashes for cross-platform assertions
    return p.replace(chr(92), "/")

def _state(*, phase, status, iteration):
    class _S:
        pass

    s = _S()
    s.phase = phase
    s.status = status
    s.current_iteration = iteration
    return s


def test_init_emits_json_only(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    def fake_initialize_run(self, **kwargs):
        return "sess_123"

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope",
                "domain",
                "--entity",
                "Foo",
                "--table",
                "foo",
                "--bounded-context",
                "bc",
            ],
            prog_name="aiwf",
        )

    assert result.exit_code == 0
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "init"
    assert obj["session_id"] == "sess_123"
    assert obj["exit_code"] == 0
    assert result.output.endswith("\n")
    assert result.output.count("\n") == 1


def test_step_emits_json_only_awaiting(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    def fake_step(self, session_id: str):
        return _state(
            phase=WorkflowPhase.REVIEWING,
            status=WorkflowStatus.IN_PROGRESS,
            iteration=1,
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        root = Path(".aiwf")
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", root, raising=True)

        # Create prompt only => awaiting response
        # Updated: iteration-1 directly
        prompt = root / "sess_123" / "iteration-1" / "review-prompt.md"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("# prompt", encoding="utf-8")

        result = runner.invoke(cli, ["--json", "step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 2
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "step"
    assert obj["session_id"] == "sess_123"
    assert obj["exit_code"] == result.exit_code
    assert obj["phase"] == "REVIEWING"
    assert obj["status"] == "IN_PROGRESS"
    assert obj["iteration"] == 1
    assert obj["noop_awaiting_artifact"] is True
    assert isinstance(obj["awaiting_paths"], list)
    assert len(obj["awaiting_paths"]) == 2

    # Updated assertions
    assert any(_norm(p).endswith("iteration-1/review-prompt.md") for p in obj["awaiting_paths"])
    assert any(_norm(p).endswith("iteration-1/review-response.md") for p in obj["awaiting_paths"])

    assert result.output.count("\n") == 1


def test_step_json_prompt_and_response_present_exit_0(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    def fake_step(self, session_id: str):
        return _state(
            phase=WorkflowPhase.REVIEWING,
            status=WorkflowStatus.IN_PROGRESS,
            iteration=1,
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        root = Path(".aiwf")
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", root, raising=True)

        # Create both prompt + response => NOT awaiting
        # Updated: iteration-1 directly
        prompt = root / "sess_123" / "iteration-1" / "review-prompt.md"
        response = root / "sess_123" / "iteration-1" / "review-response.md"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        response.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("# prompt", encoding="utf-8")
        response.write_text("# response", encoding="utf-8")

        result = runner.invoke(cli, ["--json", "step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "step"
    assert obj["session_id"] == "sess_123"
    assert obj["exit_code"] == 0
    assert obj["noop_awaiting_artifact"] is False
    assert obj["awaiting_paths"] == []
    assert result.output.count("\n") == 1


def test_status_emits_json_only(monkeypatch):
    import aiwf.domain.persistence.session_store as ss_mod
    import aiwf.cli as cli_mod

    def fake_load(self, session_id: str):
        return _state(
            phase=WorkflowPhase.REVIEWING,
            status=WorkflowStatus.IN_PROGRESS,
            iteration=1,
        )

    monkeypatch.setattr(ss_mod.SessionStore, "load", fake_load, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["--json", "status", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "status"
    assert obj["session_id"] == "sess_123"
    assert obj["phase"] == "REVIEWING"
    assert obj["status"] == "IN_PROGRESS"
    assert obj["iteration"] == 1
    assert "sess_123" in obj["session_path"]
    assert obj["exit_code"] == 0
    assert result.output.count("\n") == 1


def test_exception_path_json_status(monkeypatch):
    import aiwf.domain.persistence.session_store as ss_mod
    import aiwf.cli as cli_mod

    def fake_load(self, session_id: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(ss_mod.SessionStore, "load", fake_load, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["--json", "status", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    obj = json.loads(result.output)
    assert obj["schema_version"] == 1
    assert obj["command"] == "status"
    assert obj["exit_code"] == 1
    assert obj["session_id"] == "sess_123"
    assert "error" in obj
    assert "boom" in obj["error"]
    assert result.output.count("\n") == 1

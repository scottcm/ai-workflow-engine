from pathlib import Path
from click.testing import CliRunner

from aiwf.cli import cli
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus


def _state(*, phase, status, iteration):
    class _S:
        pass

    s = _S()
    s.phase = phase
    s.status = status
    s.current_iteration = iteration
    return s


def test_status_basic_output(monkeypatch):
    import aiwf.cli as cli_mod
    import aiwf.domain.persistence.session_store as ss_mod

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
        result = runner.invoke(cli, ["status", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    assert "phase=" in result.output
    assert "status=" in result.output
    assert "iteration=" in result.output
    assert "session_path=" in result.output
    assert "sess_123" in result.output


def test_status_terminal_state_has_summary_and_no_guidance_paths(monkeypatch):
    import aiwf.cli as cli_mod
    import aiwf.domain.persistence.session_store as ss_mod

    def fake_load(self, session_id: str):
        return _state(
            phase=WorkflowPhase.COMPLETE,
            status=WorkflowStatus.SUCCESS,
            iteration=1,
        )

    monkeypatch.setattr(ss_mod.SessionStore, "load", fake_load, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["status", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    assert "phase=COMPLETE" in result.output
    assert "status=SUCCESS" in result.output

    # Descriptive-only: should not reference prompts/responses directories or filenames.
    assert "prompts" not in result.output.lower()
    assert "responses" not in result.output.lower()


def test_status_exception_exit_1(monkeypatch):
    import aiwf.cli as cli_mod
    import aiwf.domain.persistence.session_store as ss_mod

    def fake_load(self, session_id: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(ss_mod.SessionStore, "load", fake_load, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["status", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    assert "boom" in result.output

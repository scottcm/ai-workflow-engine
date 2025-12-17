from pathlib import Path

from click.testing import CliRunner

from aiwf.cli import cli
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus


def _state(*, phase, status, iteration):
    class _S:
        pass

    s = _S()
    s.phase = phase
    s.status = status
    s.current_iteration = iteration
    return s


def test_step_advances_exit_0_and_header_present(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    calls = {"step": 0, "init_called": False}

    def fake_initialize_run(*args, **kwargs):
        calls["init_called"] = True
        raise AssertionError("initialize_run must not be called by step")

    def fake_step(self, session_id: str):
        calls["step"] += 1
        return _state(
            phase=WorkflowPhase.GENERATING,
            status=WorkflowStatus.IN_PROGRESS,
            iteration=1,
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)
    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    assert "phase=" in result.output
    assert "status=" in result.output
    assert "iteration=" in result.output
    assert calls["step"] == 1
    assert calls["init_called"] is False


def test_step_awaiting_artifact_exit_2_and_outputs_paths(monkeypatch) -> None:
    """
    Awaiting-artifact is inferred via filesystem (manual UX):
    prompt exists AND response missing under iteration-scoped dirs.
    """
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

        session_id = "sess_123"
        iteration = 1

        # IMPORTANT: match cli.py path logic exactly:
        #   root/session_id/iteration-<n>/<PROMPTS_DIR>/<review-prompt.md>
        # and DO NOT create the response file.
        prompt = root / session_id / f"iteration-{iteration}" / PROMPTS_DIR / "review-prompt.md"
        response = root / session_id / f"iteration-{iteration}" / RESPONSES_DIR / "review-response.md"

        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("# review prompt", encoding="utf-8")

        result = runner.invoke(cli, ["step", session_id], prog_name="aiwf")

    assert result.exit_code == 2
    assert "noop_awaiting_artifact=true" in result.output
    assert str(prompt) in result.output
    assert str(response) in result.output  # printed as expected location even if missing


def test_step_prompt_and_response_present_exit_0(monkeypatch):
    """
    Regression guard: if both prompt and response exist, we are NOT awaiting,
    so step must exit 0 (not 2).
    """
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

        session_dir = root / "sess_123"
        iteration_dir = session_dir / "iteration-1"

        prompt = iteration_dir / PROMPTS_DIR / "review-prompt.md"
        response = iteration_dir / RESPONSES_DIR / "review-response.md"

        prompt.parent.mkdir(parents=True, exist_ok=True)
        response.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("# review prompt", encoding="utf-8")
        response.write_text("review response", encoding="utf-8")

        result = runner.invoke(cli, ["step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    assert "noop_awaiting_artifact=false" in result.output

def test_step_terminal_success_exit_0(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    def fake_step(self, session_id: str):
        return _state(
            phase=WorkflowPhase.COMPLETE,
            status=WorkflowStatus.SUCCESS,
            iteration=1,
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 0
    assert "phase=COMPLETE" in result.output
    assert "status=SUCCESS" in result.output


def test_step_cancelled_exit_3(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    def fake_step(self, session_id: str):
        return _state(
            phase=WorkflowPhase.REVIEWING,
            status=WorkflowStatus.CANCELLED,
            iteration=1,
        )

    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 3
    assert "status=CANCELLED" in result.output


def test_step_exception_exit_1(monkeypatch):
    import aiwf.application.workflow_orchestrator as wo
    import aiwf.cli as cli_mod

    def fake_step(self, session_id: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)
        result = runner.invoke(cli, ["step", "sess_123"], prog_name="aiwf")

    assert result.exit_code == 1
    assert "boom" in result.output

from pathlib import Path
from click.testing import CliRunner
from aiwf.cli import cli
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus


def test_init_success_prints_only_session_id_and_calls_orchestrator_once(monkeypatch) -> None:
    """
    Success path:
    - CLI instantiates WorkflowOrchestrator and calls initialize_run as an instance method
    - passes default profile/providers
    - MUST NOT call step()
    - prints ONLY the returned session_id to stdout (single line)
    - runs hermetically (isolated filesystem)
    """
    calls: dict[str, object] = {"init": None, "step_called": False}

    import aiwf.application.workflow_orchestrator as wo
    import aiwf.domain.constants as constants

    def fake_initialize_run(
        self,
        *,
        profile,
        providers,
        scope,
        entity,
        table,
        bounded_context,
        dev=None,
        task_id=None,
        **kwargs,
    ):
        calls["init"] = {
            "profile": profile,
            "providers": providers,
            "scope": scope,
            "entity": entity,
            "table": table,
            "bounded_context": bounded_context,
            "dev": dev,
            "task_id": task_id,
            "extra_kwargs": dict(kwargs),
        }
        return "sess_123"

    def fake_step(self, *args, **kwargs):
        calls["step_called"] = True
        raise AssertionError("step() must not be called by aiwf init")

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)
    monkeypatch.setattr(wo.WorkflowOrchestrator, "step", fake_step, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        # Ensure any persistence touches a temp sandbox, not the developer machine.
        monkeypatch.setattr(constants, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)

        result = runner.invoke(
            cli,
            [
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
    assert result.exception is None
    assert result.output == "sess_123\n"

    assert calls["init"] == {
        "profile": "default",
        "providers": {
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        "scope": "domain",
        "entity": "Foo",
        "table": "foo",
        "bounded_context": "bc",
        "dev": None,
        "task_id": None,
        "extra_kwargs": {},
    }
    assert calls["step_called"] is False


def test_init_missing_required_option_is_nonzero_and_mentions_missing_option() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "init",
            "--scope",
            "domain",
            "--entity",
            "Foo",
            "--table",
            "foo",
            # Missing --bounded-context
        ],
        prog_name="aiwf",
    )

    assert result.exit_code != 0
    assert "Missing option" in result.output
    assert "--bounded-context" in result.output
from pathlib import Path
from click.testing import CliRunner
from aiwf.interface.cli.cli import cli
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus


def test_init_success_prints_only_session_id_and_calls_orchestrator_once(monkeypatch) -> None:
    """
    Success path:
    - CLI instantiates WorkflowOrchestrator and calls initialize_run as an instance method
    - passes profile/providers from config
    - MUST NOT call step()
    - prints ONLY the returned session_id to stdout (single line)
    - runs hermetically (isolated filesystem)
    """
    calls: dict[str, object] = {"init": None, "step_called": False}

    import aiwf.application.workflow_orchestrator as wo
    import aiwf.domain.constants as constants
    import aiwf.interface.cli.cli as cli_module

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

    # Mock load_config to return a valid profile
    def mock_load_config(**kwargs):
        return {
            "profile": "jpa-mt",
            "providers": {
                "planner": "manual",
                "generator": "manual",
                "reviewer": "manual",
                "reviser": "manual",
            },
            "dev": None,
            "default_standards_provider": "scoped-layer-fs",
        }

    monkeypatch.setattr(cli_module, "load_config", mock_load_config)
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
        "profile": "jpa-mt",
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
        "extra_kwargs": {"metadata": None, "standards_provider": "scoped-layer-fs"},
    }
    assert calls["step_called"] is False


def test_init_missing_profile_fails_with_clear_error(monkeypatch) -> None:
    """init command fails fast with clear error when no profile is configured."""
    import aiwf.interface.cli.cli as cli_module

    # Mock load_config to return no profile (the default)
    def mock_load_config(**kwargs):
        return {
            "profile": None,  # No profile configured
            "providers": {
                "planner": "manual",
                "generator": "manual",
                "reviewer": "manual",
                "reviser": "manual",
            },
            "dev": None,
            "default_standards_provider": "scoped-layer-fs",
        }

    monkeypatch.setattr(cli_module, "load_config", mock_load_config)

    runner = CliRunner()
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

    assert result.exit_code != 0
    assert "Profile is required" in result.output


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


def test_init_with_schema_file_stores_path_in_metadata(monkeypatch) -> None:
    """When --schema-file is provided, path is stored in metadata (not content)."""
    calls: dict[str, object] = {"init": None}

    import aiwf.application.workflow_orchestrator as wo
    import aiwf.domain.constants as constants
    import aiwf.interface.cli.cli as cli_module

    def fake_initialize_run(self, *, metadata=None, **kwargs):
        calls["init"] = {"metadata": metadata, **kwargs}
        return "sess_456"

    # Mock load_config to return a valid profile
    def mock_load_config(**kwargs):
        return {
            "profile": "jpa-mt",
            "providers": {"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
            "dev": None,
            "default_standards_provider": "scoped-layer-fs",
        }

    monkeypatch.setattr(cli_module, "load_config", mock_load_config)
    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(constants, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)

        result = runner.invoke(
            cli,
            [
                "init",
                "--scope", "domain",
                "--entity", "Foo",
                "--table", "foo",
                "--bounded-context", "bc",
                "--schema-file", "schema.sql",
            ],
            prog_name="aiwf",
        )

    # Path stored, not content - file existence not checked at init time
    assert result.exit_code == 0
    assert result.output == "sess_456\n"
    assert calls["init"]["metadata"] == {"schema_file": "schema.sql"}


def test_init_uses_config_default_standards_provider(monkeypatch) -> None:
    """CLI uses default_standards_provider from config when no CLI arg provided."""
    calls: dict[str, object] = {"init": None}

    import aiwf.application.workflow_orchestrator as wo
    import aiwf.domain.constants as constants
    import aiwf.interface.cli.cli as cli_module

    def fake_initialize_run(self, *, standards_provider=None, **kwargs):
        calls["init"] = {"standards_provider": standards_provider, **kwargs}
        return "sess_789"

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)

    # Mock load_config to return a custom default_standards_provider
    def mock_load_config(**kwargs):
        return {
            "profile": "jpa-mt",
            "providers": {"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
            "dev": None,
            "default_standards_provider": "custom-config-provider",
        }

    monkeypatch.setattr(cli_module, "load_config", mock_load_config)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(constants, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)

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

    assert result.exit_code == 0
    assert result.output == "sess_789\n"
    # Should use config's default_standards_provider
    assert calls["init"]["standards_provider"] == "custom-config-provider"


def test_init_cli_arg_overrides_config_default_standards_provider(monkeypatch) -> None:
    """CLI --standards-provider arg overrides config default."""
    calls: dict[str, object] = {"init": None}

    import aiwf.application.workflow_orchestrator as wo
    import aiwf.domain.constants as constants
    import aiwf.interface.cli.cli as cli_module

    def fake_initialize_run(self, *, standards_provider=None, **kwargs):
        calls["init"] = {"standards_provider": standards_provider, **kwargs}
        return "sess_abc"

    monkeypatch.setattr(wo.WorkflowOrchestrator, "initialize_run", fake_initialize_run, raising=True)

    # Mock load_config to return a different default
    def mock_load_config(**kwargs):
        return {
            "profile": "jpa-mt",
            "providers": {"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
            "dev": None,
            "default_standards_provider": "config-provider",
        }

    monkeypatch.setattr(cli_module, "load_config", mock_load_config)

    runner = CliRunner()
    with runner.isolated_filesystem():
        monkeypatch.setattr(constants, "DEFAULT_SESSIONS_ROOT", Path(".aiwf"), raising=True)

        result = runner.invoke(
            cli,
            [
                "init",
                "--scope", "domain",
                "--entity", "Foo",
                "--table", "foo",
                "--bounded-context", "bc",
                "--standards-provider", "cli-override-provider",
            ],
            prog_name="aiwf",
        )

    assert result.exit_code == 0
    assert result.output == "sess_abc\n"
    # CLI arg should override config default
    assert calls["init"]["standards_provider"] == "cli-override-provider"
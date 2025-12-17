import click
@click.group(help="AI Workflow Engine CLI.")
def cli() -> None:
    """Root CLI command group."""
    pass


@cli.command("init")
@click.option("--scope", required=True, type=str)
@click.option("--entity", required=True, type=str)
@click.option("--table", required=True, type=str)
@click.option("--bounded-context", required=True, type=str)
@click.option("--dev", required=False, type=str)
@click.option("--task-id", "task_id", required=False, type=str)
def init_cmd(
    scope: str,
    entity: str,
    table: str,
    bounded_context: str,
    dev: str | None,
    task_id: str | None,
) -> None:
    """
    Initialize a new workflow session (Slice B).

    Slice B is wiring only: no config loading yet and no workflow decisions here.
    """
    # Locked temporary defaults until config slice lands.
    profile = "default"
    providers = {
        "planner": "manual",
        "generator": "manual",
        "reviewer": "manual",
        "reviser": "manual",
    }

    try:
        # Import inside command to minimize import-time side effects.
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.constants import DEFAULT_SESSIONS_ROOT
        from aiwf.domain.persistence.session_store import SessionStore

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
        )

        session_id = orchestrator.initialize_run(
            profile=profile,
            providers=providers,
            scope=scope,
            entity=entity,
            table=table,
            bounded_context=bounded_context,
            dev=dev,
            task_id=task_id,
        )

        # Locked output contract: ONLY the id, single line, stdout.
        click.echo(session_id, nl=True)
    except Exception as e:
        # Errors to stderr + non-zero exit.
        raise click.ClickException(str(e)) from e

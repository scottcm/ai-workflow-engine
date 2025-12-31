"""JPA Multi-Tenant Profile package."""

import click
from pathlib import Path

from aiwf.domain.models.workflow_state import ExecutionMode

from .jpa_mt_profile import JpaMtProfile

__all__ = ["JpaMtProfile", "register"]


def register(cli_group: click.Group) -> type:
    """Register jpa-mt commands and return profile class.

    Args:
        cli_group: The Click group to add profile commands to.

    Returns:
        The JpaMtProfile class for factory registration.
    """

    @cli_group.command("init")
    @click.option(
        "--scope",
        required=True,
        type=click.Choice(["domain", "vertical"]),
        help="Layer scope: domain (entity+repo) or vertical (full stack)",
    )
    @click.option("--entity", required=True, help="Entity name (e.g., Customer)")
    @click.option("--table", required=True, help="Database table name")
    @click.option("--bounded-context", required=True, help="DDD bounded context")
    @click.option(
        "--schema-file",
        required=True,
        type=click.Path(exists=True),
        help="Path to schema DDL file",
    )
    @click.option("--dev", default=None, help="Developer identifier")
    @click.option("--task-id", default=None, help="Task/ticket identifier")
    @click.option(
        "--execution-mode",
        type=click.Choice(["interactive", "automated"]),
        default="interactive",
        help="Execution mode: interactive (user runs step/approve) or automated (engine auto-advances)",
    )
    @click.option("--planner", default="manual", help="Provider for planning phase")
    @click.option("--generator", default="manual", help="Provider for generation phase")
    @click.option("--reviewer", default="manual", help="Provider for review phase")
    @click.option("--revisor", default="manual", help="Provider for revision phase")
    @click.pass_context
    def init(
        ctx,
        scope,
        entity,
        table,
        bounded_context,
        schema_file,
        dev,
        task_id,
        execution_mode,
        planner,
        generator,
        reviewer,
        revisor,
    ):
        """Initialize a new JPA multi-tenant workflow session."""
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore
        from aiwf.interface.cli.cli import DEFAULT_SESSIONS_ROOT
        from aiwf.interface.cli.output_models import InitOutput

        # Get JSON mode from parent context
        json_mode = ctx.obj.get("json", False) if ctx.obj else False

        # Build context from CLI args
        context = {
            "scope": scope,
            "entity": entity,
            "table": table,
            "bounded_context": bounded_context,
            "schema_file": str(Path(schema_file).resolve()),
        }
        if dev:
            context["dev"] = dev
        if task_id:
            context["task_id"] = task_id

        # Build providers dict
        providers = {
            "planner": planner,
            "generator": generator,
            "reviewer": reviewer,
            "reviser": revisor,
        }

        try:
            # Initialize session
            session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
            orchestrator = WorkflowOrchestrator(
                session_store=session_store,
                sessions_root=DEFAULT_SESSIONS_ROOT,
            )
            exec_mode = (
                ExecutionMode.AUTOMATED
                if execution_mode == "automated"
                else ExecutionMode.INTERACTIVE
            )

            session_id = orchestrator.initialize_run(
                profile="jpa-mt",
                context=context,
                execution_mode=exec_mode,
                providers=providers,
            )

            # Transition from INIT to PLAN[PROMPT] and create the planning prompt
            state = orchestrator.init(session_id)

            # Emit progress messages
            for msg in getattr(state, "messages", []):
                if not json_mode:
                    click.echo(msg, err=True)

            if json_mode:
                click.echo(
                    InitOutput(exit_code=0, session_id=session_id).model_dump_json(
                        exclude_none=True
                    )
                )
                raise click.exceptions.Exit(0)

            click.echo(f"Session initialized: {session_id}")
            click.echo(f"Entity: {entity}")
            click.echo(f"Scope: {scope}")

        except click.exceptions.Exit:
            raise
        except Exception as e:
            if json_mode:
                click.echo(
                    InitOutput(exit_code=1, error=str(e)).model_dump_json(
                        exclude_none=True
                    )
                )
                raise click.exceptions.Exit(1)
            raise click.ClickException(str(e)) from e

    @cli_group.command("schema-info")
    @click.argument("session_id")
    @click.pass_context
    def schema_info(ctx, session_id):
        """Display parsed schema information for a session."""
        from aiwf.domain.persistence.session_store import SessionStore
        from aiwf.interface.cli.cli import DEFAULT_SESSIONS_ROOT

        json_mode = ctx.obj.get("json", False) if ctx.obj else False

        try:
            session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
            state = session_store.load(session_id)

            schema_file = state.context.get("schema_file")
            if not schema_file:
                msg = "No schema file in session context"
                if json_mode:
                    click.echo(f'{{"error": "{msg}", "exit_code": 1}}')
                    raise click.exceptions.Exit(1)
                click.echo(msg, err=True)
                raise click.exceptions.Exit(1)

            if json_mode:
                import json

                click.echo(
                    json.dumps(
                        {
                            "exit_code": 0,
                            "session_id": session_id,
                            "schema_file": schema_file,
                            "table": state.context.get("table"),
                            "entity": state.context.get("entity"),
                        }
                    )
                )
                raise click.exceptions.Exit(0)

            click.echo(f"Schema file: {schema_file}")
            click.echo(f"Table: {state.context.get('table')}")
            click.echo(f"Entity: {state.context.get('entity')}")

        except click.exceptions.Exit:
            raise
        except Exception as e:
            if json_mode:
                click.echo(f'{{"error": "{e}", "exit_code": 1}}')
                raise click.exceptions.Exit(1)
            raise click.ClickException(str(e)) from e

    @cli_group.command("layers")
    @click.pass_context
    def layers(ctx):
        """List available layer scopes for JPA-MT profile."""
        json_mode = ctx.obj.get("json", False) if ctx.obj else False

        if json_mode:
            import json

            click.echo(json.dumps({"exit_code": 0, "layers": ["domain", "vertical"]}))
            raise click.exceptions.Exit(0)

        click.echo("Available scopes:")
        click.echo("  domain   - Entity class + Repository interface")
        click.echo("  vertical - Full vertical slice (future)")

    @cli_group.command("info")
    def info():
        """Show jpa-mt profile information."""
        click.echo("JPA Multi-Tenant Profile")
        click.echo("Use 'aiwf jpa-mt init' to start a new session.")

    return JpaMtProfile
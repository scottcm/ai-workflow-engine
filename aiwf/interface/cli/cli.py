import click
from pathlib import Path
from pydantic import BaseModel

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus
from aiwf.interface.cli.output_models import InitOutput, StatusOutput, StepOutput
from aiwf.application.config_loader import load_config
from aiwf.application.approval_specs import ING_APPROVAL_SPECS


# Patched by tests where the CLI reads it.
DEFAULT_SESSIONS_ROOT = Path(".aiwf")


def _json_emit(model: BaseModel) -> None:
    # Single-line JSON, omit None fields (e.g., InitOutput.session_id on error).
    click.echo(model.model_dump_json(exclude_none=True), nl=True)


def _get_json_mode(ctx: click.Context) -> bool:
    obj = ctx.obj or {}
    return bool(obj.get("json", False))


def _awaiting_paths_for_state(session_id: str, state) -> tuple[bool, list[str]]:
    """
    Manual-workflow inference (Slice C): prompt exists + response missing => awaiting response.
    Returns (awaiting, [prompt_path, response_path]) for mapped phases; otherwise (False, []).
    """
    if state.phase not in ING_APPROVAL_SPECS:
        return False, []

    spec = ING_APPROVAL_SPECS[state.phase]
    
    # Resolve templates
    prompt_rel = spec.prompt_relpath_template
    response_rel = spec.response_relpath_template
    
    iteration = getattr(state, "current_iteration", 1)
    
    if "{N}" in prompt_rel:
        prompt_rel = prompt_rel.format(N=iteration)
    if "{N}" in response_rel:
        response_rel = response_rel.format(N=iteration)

    session_dir = DEFAULT_SESSIONS_ROOT / session_id
    prompt_path = session_dir / prompt_rel
    response_path = session_dir / response_rel

    awaiting = prompt_path.exists() and not response_path.exists()
    return awaiting, [str(prompt_path), str(response_path)]


@click.group(help="AI Workflow Engine CLI.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON on stdout.")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json"] = bool(json_output)


@cli.command("init")
@click.option("--scope", required=True, type=str)
@click.option("--entity", required=True, type=str)
@click.option("--table", required=True, type=str)
@click.option("--bounded-context", required=True, type=str)
@click.option("--dev", required=False, type=str)
@click.option("--task-id", "task_id", required=False, type=str)
@click.pass_context
def init_cmd(
    ctx: click.Context,
    scope: str,
    entity: str,
    table: str,
    bounded_context: str,
    dev: str | None,
    task_id: str | None,
) -> None:

    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore

        cfg = load_config(project_root=Path.cwd(), user_home=Path.home())

        profile = cfg["profile"]
        providers = cfg["providers"]

        # CLI --dev overrides config; config overrides default
        dev = dev if dev is not None else cfg["dev"]

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

        if _get_json_mode(ctx):
            _json_emit(
                InitOutput(
                    exit_code=0,
                    session_id=session_id,
                )
            )
            raise click.exceptions.Exit(0)

        click.echo(session_id, nl=True)
    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                InitOutput(
                    exit_code=1,
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e


@cli.command("step")
@click.argument("session_id", type=str)
@click.pass_context
def step_cmd(ctx: click.Context, session_id: str) -> None:
    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
        )

        state = orchestrator.step(session_id)

        phase = state.phase.name
        status = state.status.name
        iteration = getattr(state, "current_iteration", None)

        awaiting, paths = _awaiting_paths_for_state(session_id, state)

        exit_code = 0
        if state.status == WorkflowStatus.CANCELLED:
            exit_code = 3
        elif awaiting:
            exit_code = 2

        if _get_json_mode(ctx):
            _json_emit(
                StepOutput(
                    exit_code=exit_code,
                    session_id=session_id,
                    phase=phase,
                    status=status,
                    iteration=iteration,
                    noop_awaiting_artifact=awaiting,
                    awaiting_paths=paths if awaiting else [],
                )
            )
            raise click.exceptions.Exit(exit_code)

        header = (
            f"phase={phase} "
            f"status={status} "
            f"iteration={iteration} "
            f"noop_awaiting_artifact={'true' if awaiting else 'false'}"
        )
        click.echo(header)

        if awaiting:
            for p in paths:
                click.echo(p)
            raise click.exceptions.Exit(2)

        if exit_code == 3:
            raise click.exceptions.Exit(3)

    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                StepOutput(
                    exit_code=1,
                    session_id=session_id,
                    phase="",
                    status="",
                    iteration=None,
                    noop_awaiting_artifact=False,
                    awaiting_paths=[],
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e


@cli.command("status")
@click.argument("session_id", type=str)
@click.pass_context
def status_cmd(ctx: click.Context, session_id: str) -> None:
    try:
        from aiwf.domain.persistence.session_store import SessionStore

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        state = session_store.load(session_id)
        session_path = str(DEFAULT_SESSIONS_ROOT / session_id)

        phase = state.phase.name
        status = state.status.name
        iteration = getattr(state, "current_iteration", None)

        if _get_json_mode(ctx):
            _json_emit(
                StatusOutput(
                    exit_code=0,
                    session_id=session_id,
                    phase=phase,
                    status=status,
                    iteration=iteration,
                    session_path=session_path,
                )
            )
            raise click.exceptions.Exit(0)

        click.echo(f"phase={phase}")
        click.echo(f"status={status}")
        click.echo(f"iteration={iteration}")
        click.echo(f"session_path={session_path}")

    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                StatusOutput(
                    exit_code=1,
                    session_id=session_id,
                    phase="",
                    status="",
                    iteration=None,
                    session_path=str(DEFAULT_SESSIONS_ROOT / session_id),
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e

@cli.command("approve")
@click.argument("session_id", type=str)
@click.option("--hash-prompts", is_flag=True, help="Hash prompts.")
@click.option("--no-hash-prompts", is_flag=True, help="Do not hash prompts.")
@click.pass_context
def approve_cmd(ctx: click.Context, session_id: str, hash_prompts: bool, no_hash_prompts: bool) -> None:
    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore

        cfg = load_config(project_root=Path.cwd(), user_home=Path.home())
        
        # Determine effective hash_prompts
        effective_hash = cfg.get("hash_prompts", False)
        if hash_prompts:
            effective_hash = True
        elif no_hash_prompts:
            effective_hash = False

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
        )

        # Call orchestrator.approve
        state = orchestrator.approve(session_id, hash_prompts=effective_hash)

        if state.status == WorkflowStatus.ERROR:
            # Orchestrator should have printed the error message already
            raise click.exceptions.Exit(1)
            
    except click.exceptions.Exit:
        raise
    except Exception as e:
        # If unexpected error
        click.echo(f"Cannot approve: {e}", err=True)
        raise click.exceptions.Exit(1)

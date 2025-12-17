import click
from pathlib import Path
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR
from aiwf.domain.models.workflow_state import WorkflowPhase


DEFAULT_SESSIONS_ROOT = Path(".aiwf")


@click.group(help="AI Workflow Engine CLI.")
def cli() -> None:
    pass


@cli.command("step")
@click.argument("session_id", type=str)
def step_cmd(session_id: str) -> None:
    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore
        from aiwf.domain.models.workflow_state import WorkflowStatus

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
        )

        state = orchestrator.step(session_id)

        phase_str = state.phase.name
        status_str = state.status.name
        iteration = state.current_iteration

        # Awaiting-artifact inference via filesystem (manual UX)
        phase_to_files = {
            WorkflowPhase.PLANNING: ("planning-prompt.md", "planning-response.md"),
            WorkflowPhase.GENERATING: ("generation-prompt.md", "generation-response.md"),
            WorkflowPhase.REVIEWING: ("review-prompt.md", "review-response.md"),
            WorkflowPhase.REVISING: ("revision-prompt.md", "revision-response.md"),
        }

        awaiting_paths: list[str] = []

        session_dir = DEFAULT_SESSIONS_ROOT / session_id

        prompt_name, response_name = phase_to_files.get(state.phase, (None, None))
        if prompt_name and response_name:
            # Planning artifacts live at session root; others live under iteration-N.
            if state.phase == WorkflowPhase.PLANNING:
                prompt_path = session_dir / PROMPTS_DIR / prompt_name
                response_path = session_dir / RESPONSES_DIR / response_name
            else:
                iteration_dir = session_dir / f"iteration-{iteration}"
                prompt_path = iteration_dir / PROMPTS_DIR / prompt_name
                response_path = iteration_dir / RESPONSES_DIR / response_name

            # Emit guidance paths if they exist (manual UX)
            if prompt_path.exists():
                awaiting_paths.append(str(prompt_path))
            if response_path.exists():
                awaiting_paths.append(str(response_path))


        header = (
            f"phase={phase_str} "
            f"status={status_str} "
            f"iteration={iteration} "
            f"noop_awaiting_artifact={'true' if awaiting_paths else 'false'}"
        )
        click.echo(header)

        if status_str == "CANCELLED":
            raise click.exceptions.Exit(3)

        if awaiting_paths:
            for p in awaiting_paths:
                click.echo(p)
            raise click.exceptions.Exit(2)

    except click.exceptions.Exit:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from e

"""JPA-MT Profile CLI Commands (v2).

Multi-tenant JPA code generation for Spring/Hibernate environments.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import click

from .config import JpaMtConfig
from .profile import JpaMtProfile
# Note: yaml-rules provider is registered in profile.py when JpaMtProfile is imported

if TYPE_CHECKING:
    from aiwf.domain.profiles.workflow_profile import WorkflowProfile


def _get_config() -> JpaMtConfig:
    """Load profile configuration."""
    config_path = Path(__file__).parent / "config.yml"
    if config_path.exists():
        return JpaMtConfig.from_yaml(config_path)
    return JpaMtConfig()


def create_profile() -> JpaMtProfile:
    """Factory function for profile registration."""
    return JpaMtProfile(_get_config())


def register(cli_group: click.Group) -> type["WorkflowProfile"]:
    """Entry point for profile registration (called by plugin system).

    Args:
        cli_group: Click group to register commands under

    Returns:
        Profile class for factory registration
    """

    @cli_group.command("info")
    def info() -> None:
        """Show jpa-mt profile information."""
        metadata = JpaMtProfile.get_metadata()
        click.echo(f"Profile: {metadata['name']}")
        click.echo(f"Description: {metadata['description']}")
        click.echo(f"Target Stack: {metadata['target_stack']}")
        click.echo(f"Scopes: {', '.join(metadata['scopes'])}")

    @cli_group.command("init")
    @click.option(
        "--scope",
        type=click.Choice(["domain", "service", "api", "full"]),
        default="domain",
        help="Artifact scope to generate",
    )
    @click.option("--entity", required=True, help="Entity name (e.g., Customer)")
    @click.option("--table", required=True, help="Database table name (e.g., app.customers)")
    @click.option("--bounded-context", required=True, help="DDD bounded context (e.g., client)")
    @click.option("--schema-file", required=True, type=click.Path(exists=True), help="Path to schema DDL file")
    @click.option("--design", type=click.Path(exists=True), help="Path to design document (optional)")
    @click.option("--conventions", help="Named convention set from conventions.json (e.g., control-plane)")
    @click.option("--dev", help="Developer identifier")
    @click.option("--task-id", help="Task/ticket identifier")
    @click.option("--planner", help="Provider for planning phase")
    @click.option("--generator", help="Provider for generation phase")
    @click.option("--reviewer", help="Provider for review phase")
    @click.option("--revisor", help="Provider for revision phase")
    @click.pass_context
    def init(
        ctx: click.Context,
        scope: str,
        entity: str,
        table: str,
        bounded_context: str,
        schema_file: str,
        design: str | None,
        conventions: str | None,
        dev: str | None,
        task_id: str | None,
        planner: str | None,
        generator: str | None,
        reviewer: str | None,
        revisor: str | None,
    ) -> None:
        """Initialize a new JPA multi-tenant workflow session."""
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.interface.cli.output_models import InitOutput

        # Build context for profile
        context = {
            "scope": scope,
            "entity": entity,
            "table": table,
            "bounded_context": bounded_context,
            "schema_file": schema_file,
        }

        if design:
            context["design"] = design
        if conventions:
            context["conventions"] = conventions

        # Build metadata
        metadata = {}
        if dev:
            metadata["developer"] = dev
        if task_id:
            metadata["task_id"] = task_id

        # Build provider overrides
        providers = {}
        if planner:
            providers["planner"] = planner
        if generator:
            providers["generator"] = generator
        if reviewer:
            providers["reviewer"] = reviewer
        if revisor:
            providers["revisor"] = revisor

        try:
            from aiwf.domain.persistence.session_store import SessionStore
            from aiwf.interface.cli.cli import _get_sessions_root

            sessions_root = _get_sessions_root(ctx)
            session_store = SessionStore(sessions_root=sessions_root)
            orchestrator = WorkflowOrchestrator(
                session_store=session_store,
                sessions_root=sessions_root,
            )
            # Default providers if not specified
            default_providers = {
                "planner": "manual",
                "generator": "manual",
                "reviewer": "manual",
                "revisor": "manual",
            }
            default_providers.update(providers)

            session_id = orchestrator.initialize_run(
                profile="jpa-mt",
                context=context,
                metadata=metadata if metadata else None,
                providers=default_providers,
            )

            result = InitOutput(
                exit_code=0,
                session_id=session_id,
            )
            click.echo(result.model_dump_json(indent=2))

        except Exception as e:
            result = InitOutput(
                exit_code=1,
                session_id="",
                error=str(e),
            )
            click.echo(result.model_dump_json(indent=2))
            raise SystemExit(1)

    @cli_group.command("scopes")
    def scopes() -> None:
        """List available scopes and their artifacts."""
        config = _get_config()

        click.echo("Available scopes:\n")
        for name, scope_config in config.scopes.items():
            click.echo(f"  {name}:")
            click.echo(f"    Description: {scope_config.description}")
            click.echo(f"    Artifacts: {', '.join(scope_config.artifacts)}")
            click.echo()

    return JpaMtProfile

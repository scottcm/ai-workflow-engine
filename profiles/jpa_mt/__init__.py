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
        click.echo(f"\nContext (required for init):")
        context_schema = metadata.get("context_schema", {})
        for key, spec in context_schema.items():
            required = " (required)" if spec.get("required") else ""
            default = f" [default: {spec['default']}]" if "default" in spec else ""
            click.echo(f"  {key}{required}{default}")

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

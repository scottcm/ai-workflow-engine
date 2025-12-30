"""JPA Multi-Tenant Profile package."""

import click

from .jpa_mt_profile import JpaMtProfile

__all__ = ["JpaMtProfile", "register"]


def register(cli_group: click.Group) -> type:
    """Register jpa-mt commands and return profile class.

    Full implementation in Phase 4. This stub allows discovery to work.
    """
    @cli_group.command("info")
    def info():
        """Show jpa-mt profile information."""
        click.echo("JPA Multi-Tenant Profile")
        click.echo("Use 'aiwf jpa-mt init' to start a new session.")

    return JpaMtProfile
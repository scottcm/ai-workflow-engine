import click

@click.group(help="AI Workflow Engine CLI.")
def cli() -> None:
    """Root CLI command group."""
    # Slice A: CLI scaffold only. No subcommands or wiring here yet.
    raise NotImplementedError("CLI subcommands not implemented yet.")

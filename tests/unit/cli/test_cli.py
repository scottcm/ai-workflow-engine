from click.testing import CliRunner
from aiwf.cli import cli


def test_cli_loads_and_help_works() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"], prog_name="aiwf")

    assert result.exit_code == 0
    assert result.exception is None
    assert "Usage: aiwf" in result.output

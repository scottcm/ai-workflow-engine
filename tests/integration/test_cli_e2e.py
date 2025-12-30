"""End-to-end CLI integration tests.

Tests the CLI commands (init, step, approve, status) as a user would invoke them,
verifying correct exit codes, output formats, and state transitions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.interface.cli.cli import cli


def make_runner() -> CliRunner:
    """Create a CliRunner for CLI tests.

    Note: In Click 8.x, result.stdout contains only stdout, result.stderr
    contains only stderr, and result.output contains both combined.
    For JSON parsing, use result.stdout to avoid progress messages.
    """
    return CliRunner()


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Set up CLI environment with config and standards."""
    # Create standards directory
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

    # Create stub standards files
    for filename in [
        "ORG.md",
        "NAMING_AND_API.md",
        "PACKAGES_AND_LAYERS.md",
        "JPA_AND_DATABASE.md",
        "ARCHITECTURE_AND_MULTITENANCY.md",
        "BOILERPLATE_AND_DI.md",
    ]:
        (standards_dir / filename).write_text(f"# {filename}\n\nStub content.\n")

    # Create schema file
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text(
        "CREATE TABLE app.products (id BIGINT PRIMARY KEY, name VARCHAR(255));",
        encoding="utf-8",
    )

    # Create project config
    config_dir = tmp_path / ".aiwf"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "config.yml").write_text(
        "profile: jpa-mt\nproviders:\n  planner: manual\n  generator: manual\n  reviewer: manual\n  reviser: manual\n",
        encoding="utf-8",
    )

    # Change to tmp_path for relative paths
    monkeypatch.chdir(tmp_path)

    # Patch DEFAULT_SESSIONS_ROOT
    import aiwf.interface.cli.cli as cli_mod
    sessions_root = tmp_path / ".aiwf" / "sessions"
    monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_ROOT", sessions_root)

    return {
        "tmp_path": tmp_path,
        "sessions_root": sessions_root,
        "schema_file": schema_file,
    }


class TestCliInitCommand:
    """Tests for 'aiwf init' command."""

    def test_init_creates_session_plain_text(self, cli_env):
        """init command creates session and outputs session ID."""
        runner = make_runner()

        result = runner.invoke(
            cli,
            [
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )

        assert result.exit_code == 0
        session_id = result.stdout.strip()
        assert len(session_id) > 0

        # Verify session was created
        session_dir = cli_env["sessions_root"] / session_id
        assert session_dir.exists()
        assert (session_dir / "session.json").exists()

    def test_init_creates_session_json_output(self, cli_env):
        """init command with --json outputs proper JSON."""
        runner = make_runner()

        result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["schema_version"] == 1
        assert output["command"] == "init"
        assert output["exit_code"] == 0
        assert "session_id" in output
        assert len(output["session_id"]) > 0

    def test_init_missing_required_arg_fails(self, cli_env):
        """init command without required args fails."""
        runner = make_runner()

        result = runner.invoke(
            cli,
            ["init", "--scope", "domain"],  # Missing --entity, --table, --bounded-context
        )

        assert result.exit_code != 0


class TestCliStepCommand:
    """Tests for 'aiwf step' command."""

    def test_step_advances_phase_and_generates_prompt(self, cli_env):
        """step command advances workflow phase and generates prompt."""
        runner = make_runner()

        # First, create a session
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )
        session_id = json.loads(init_result.stdout)["session_id"]

        # Step to PLANNING - also generates prompt, so awaiting response (exit 2)
        step_result = runner.invoke(cli, ["step", session_id])

        # Exit code 2 means awaiting response (prompt generated)
        assert step_result.exit_code == 2
        assert "phase=PLANNING" in step_result.stdout
        assert "status=IN_PROGRESS" in step_result.stdout
        assert "noop_awaiting_artifact=true" in step_result.stdout

    def test_step_json_output_awaiting(self, cli_env):
        """step command with --json outputs proper JSON when awaiting."""
        runner = make_runner()

        # Create session
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )
        session_id = json.loads(init_result.stdout)["session_id"]

        # Step with JSON output - generates prompt, awaiting response
        step_result = runner.invoke(cli, ["--json", "step", session_id])

        assert step_result.exit_code == 2  # Awaiting response
        output = json.loads(step_result.stdout)
        assert output["schema_version"] == 1
        assert output["command"] == "step"
        assert output["session_id"] == session_id
        assert output["phase"] == "PLANNING"
        assert output["status"] == "IN_PROGRESS"
        assert output["iteration"] == 1
        assert output["noop_awaiting_artifact"] is True

    def test_step_awaiting_response_exit_2(self, cli_env):
        """step command returns exit code 2 when awaiting response."""
        runner = make_runner()
        tmp_path = cli_env["tmp_path"]
        sessions_root = cli_env["sessions_root"]

        # Create session and step to PLANNING
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )
        session_id = json.loads(init_result.stdout)["session_id"]

        # Step to PLANNING
        runner.invoke(cli, ["step", session_id])

        # Step again to generate prompt (now awaiting response)
        step_result = runner.invoke(cli, ["--json", "step", session_id])

        assert step_result.exit_code == 2
        output = json.loads(step_result.stdout)
        assert output["noop_awaiting_artifact"] is True
        assert len(output["awaiting_paths"]) == 2  # prompt and response paths


class TestCliStatusCommand:
    """Tests for 'aiwf status' command."""

    def test_status_shows_current_state(self, cli_env):
        """status command shows current workflow state."""
        runner = make_runner()

        # Create session
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )
        session_id = json.loads(init_result.stdout)["session_id"]

        # Check status
        status_result = runner.invoke(cli, ["status", session_id])

        assert status_result.exit_code == 0
        assert "phase=INITIALIZED" in status_result.stdout
        assert "status=IN_PROGRESS" in status_result.stdout
        assert "iteration=1" in status_result.stdout

    def test_status_json_output(self, cli_env):
        """status command with --json outputs proper JSON."""
        runner = make_runner()

        # Create session
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )
        session_id = json.loads(init_result.stdout)["session_id"]

        # Step to change state
        runner.invoke(cli, ["step", session_id])

        # Check status with JSON
        status_result = runner.invoke(cli, ["--json", "status", session_id])

        assert status_result.exit_code == 0
        output = json.loads(status_result.stdout)
        assert output["schema_version"] == 1
        assert output["command"] == "status"
        assert output["session_id"] == session_id
        assert output["phase"] == "PLANNING"
        assert "session_path" in output

    def test_status_nonexistent_session_fails(self, cli_env):
        """status command with non-existent session fails."""
        runner = make_runner()

        result = runner.invoke(cli, ["--json", "status", "nonexistent-session"])

        assert result.exit_code == 1
        output = json.loads(result.stdout)
        assert "error" in output


class TestCliApproveCommand:
    """Tests for 'aiwf approve' command."""

    def test_approve_hashes_artifacts(self, cli_env):
        """approve command hashes code artifacts."""
        runner = make_runner()
        sessions_root = cli_env["sessions_root"]

        # Create session and advance to GENERATED
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Product",
                "--table", "app.products",
                "--bounded-context", "catalog",
                "--schema-file", "schema.sql",
            ],
        )
        session_id = json.loads(init_result.stdout)["session_id"]
        session_dir = sessions_root / session_id

        # Step to PLANNING
        runner.invoke(cli, ["step", session_id])
        runner.invoke(cli, ["step", session_id])  # Generate prompt

        # Write planning response
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        (iteration_dir / "planning-response.md").write_text("# Plan\n\nCreate entity.")

        # Step to PLANNED
        runner.invoke(cli, ["step", session_id])

        # Manually approve plan (simulate user approval)
        from aiwf.domain.persistence.session_store import SessionStore
        store = SessionStore(sessions_root=sessions_root)
        state = store.load(session_id)
        state.plan_approved = True
        store.save(state)

        # Step to GENERATING
        runner.invoke(cli, ["step", session_id])
        runner.invoke(cli, ["step", session_id])  # Generate prompt

        # Write generation response
        (iteration_dir / "generation-response.md").write_text(
            "<<<FILE: Product.java>>>\npackage com.example;\n\npublic class Product {}\n"
        )

        # Step to GENERATED
        runner.invoke(cli, ["step", session_id])

        # Approve artifacts
        approve_result = runner.invoke(cli, ["--json", "approve", session_id])

        assert approve_result.exit_code == 0
        output = json.loads(approve_result.stdout)
        assert output["command"] == "approve"
        assert output["approved"] is True
        assert "hashes" in output
        assert len(output["hashes"]) > 0


class TestCliFullWorkflow:
    """End-to-end test of full CLI workflow."""

    def test_full_workflow_via_cli(self, cli_env):
        """Complete workflow from init to COMPLETE using only CLI commands."""
        runner = make_runner()
        sessions_root = cli_env["sessions_root"]

        # 1. Init
        init_result = runner.invoke(
            cli,
            [
                "--json",
                "init",
                "--scope", "domain",
                "--entity", "Order",
                "--table", "app.orders",
                "--bounded-context", "sales",
                "--schema-file", "schema.sql",
            ],
        )
        assert init_result.exit_code == 0
        session_id = json.loads(init_result.stdout)["session_id"]
        session_dir = sessions_root / session_id

        # Helper to step and check phase
        def step_and_check(expected_phase: str, expected_exit: int = 0):
            result = runner.invoke(cli, ["--json", "step", session_id])
            assert result.exit_code == expected_exit, f"Expected exit {expected_exit}, got {result.exit_code}: {result.output}"
            output = json.loads(result.stdout)
            assert output["phase"] == expected_phase, f"Expected {expected_phase}, got {output['phase']}"
            return output

        # 2. Step to PLANNING (also generates prompt, so awaiting response - exit 2)
        output = step_and_check("PLANNING", expected_exit=2)
        assert output["noop_awaiting_artifact"] is True

        # 3. Write planning response
        iteration_dir = session_dir / "iteration-1"
        (iteration_dir / "planning-response.md").write_text("# Order Entity Plan\n\nFields: id, customerId, total")

        # 4. Step to PLANNED
        step_and_check("PLANNED")

        # 5. Approve plan (via direct state modification - simulates user action)
        from aiwf.domain.persistence.session_store import SessionStore
        store = SessionStore(sessions_root=sessions_root)
        state = store.load(session_id)
        state.plan_approved = True
        store.save(state)

        # 6. Step to GENERATING (also generates prompt, so awaiting - exit 2)
        step_and_check("GENERATING", expected_exit=2)

        # 7. Write generation response
        (iteration_dir / "generation-response.md").write_text('''
<<<FILE: Order.java>>>
package com.example.sales;

import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Order {
    @Id
    private Long id;
    private Long customerId;
    private java.math.BigDecimal total;
}
''')

        # 8. Step to GENERATED
        step_and_check("GENERATED")

        # 9. Approve code artifacts
        approve_result = runner.invoke(cli, ["--json", "approve", session_id])
        assert approve_result.exit_code == 0

        # 10. Step to REVIEWING (also generates prompt, so awaiting - exit 2)
        step_and_check("REVIEWING", expected_exit=2)

        # 11. Write passing review
        (iteration_dir / "review-response.md").write_text("""
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

Code follows all standards.
""")

        # 12. Step to REVIEWED
        step_and_check("REVIEWED")

        # 13. Approve review
        state = store.load(session_id)
        state.review_approved = True
        store.save(state)

        # 14. Step to COMPLETE
        result = runner.invoke(cli, ["--json", "step", session_id])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["phase"] == "COMPLETE"
        assert output["status"] == "SUCCESS"

        # 15. Verify final status
        status_result = runner.invoke(cli, ["--json", "status", session_id])
        assert status_result.exit_code == 0
        status_output = json.loads(status_result.stdout)
        assert status_output["phase"] == "COMPLETE"
        assert status_output["status"] == "SUCCESS"


class TestCliProfileDiscovery:
    """Tests for profile discovery via CLI."""

    def test_help_shows_profile_command_groups(self, cli_env):
        """aiwf --help shows profile command groups."""
        runner = make_runner()

        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        # jpa-mt profile should be discovered via entry point
        assert "jpa-mt" in result.output

    def test_profiles_lists_discovered_profiles(self, cli_env):
        """aiwf profiles lists all discovered profiles."""
        runner = make_runner()

        result = runner.invoke(cli, ["profiles"])

        assert result.exit_code == 0
        assert "jpa-mt" in result.output

    def test_profiles_json_output(self, cli_env):
        """aiwf profiles --json returns profile list."""
        runner = make_runner()

        result = runner.invoke(cli, ["--json", "profiles"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["schema_version"] == 1
        assert output["command"] == "profiles"
        assert "profiles" in output
        profile_names = [p["name"] for p in output["profiles"]]
        assert "jpa-mt" in profile_names

    def test_profile_subcommand_help(self, cli_env):
        """aiwf jpa-mt --help shows profile commands."""
        runner = make_runner()

        result = runner.invoke(cli, ["jpa-mt", "--help"])

        assert result.exit_code == 0
        # The stub info command should be visible
        assert "info" in result.output

    def test_profile_info_command(self, cli_env):
        """aiwf jpa-mt info runs the stub command."""
        runner = make_runner()

        result = runner.invoke(cli, ["jpa-mt", "info"])

        assert result.exit_code == 0
        assert "JPA Multi-Tenant Profile" in result.output

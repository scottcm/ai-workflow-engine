import click
import logging
from pathlib import Path
from pydantic import BaseModel

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus

logger = logging.getLogger(__name__)
from aiwf.interface.cli.output_models import (
    ApproveOutput,
    InitOutput,
    ListOutput,
    ProfileDetail,
    ProfileSummary,
    ProfilesOutput,
    ProviderDetail,
    ProviderSummary,
    ProvidersOutput,
    SessionSummary,
    StatusOutput,
    StepOutput,
    ValidateOutput,
    ValidationResult,
)
from aiwf.application.config_loader import load_config
from aiwf.application.approval_specs import ING_APPROVAL_SPECS


# Patched by tests where the CLI reads it.
DEFAULT_SESSIONS_ROOT = Path(".aiwf/sessions")


def _json_emit(model: BaseModel) -> None:
    # Single-line JSON, omit None fields (e.g., InitOutput.session_id on error).
    click.echo(model.model_dump_json(exclude_none=True), nl=True)


def _get_json_mode(ctx: click.Context) -> bool:
    obj = ctx.obj or {}
    return bool(obj.get("json", False))


def _format_error(e: Exception) -> str:
    """Format exception into user-friendly message."""
    if isinstance(e, FileNotFoundError):
        return f"File not found: {e.filename}" if e.filename else str(e)
    if isinstance(e, ValueError):
        return str(e)
    if isinstance(e, KeyError):
        return f"Missing required field: {e.args[0]}"
    return str(e)


def _emit_progress(state) -> None:
    """Emit progress messages to stderr."""
    for msg in getattr(state, "messages", []):
        click.echo(msg, err=True)


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
@click.option("--schema-file", "schema_file", required=False, type=str)
@click.option(
    "--standards-provider",
    "standards_provider",
    required=False,
    type=str,
    help="Standards provider key (overrides profile default)",
)
@click.pass_context
def init_cmd(
    ctx: click.Context,
    scope: str,
    entity: str,
    table: str,
    bounded_context: str,
    dev: str | None,
    task_id: str | None,
    schema_file: str | None,
    standards_provider: str | None,
) -> None:

    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore

        cfg = load_config(project_root=Path.cwd(), user_home=Path.home())

        profile = cfg.get("profile")
        providers = cfg["providers"]

        # Fail fast if profile is not configured
        if not profile:
            raise click.ClickException(
                "Profile is required. Specify 'profile' in .aiwf/config.yml or use a project with a configured profile."
            )

        # CLI --dev overrides config; config overrides default
        dev = dev if dev is not None else cfg["dev"]

        # Store schema file path if provided (content read at render time)
        metadata: dict | None = None
        if schema_file:
            metadata = {"schema_file": schema_file}

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
        )

        # CLI --standards-provider overrides config default
        effective_standards_provider = standards_provider or cfg.get("default_standards_provider")

        # Build context from CLI args
        context = {
            "scope": scope,
            "entity": entity,
            "table": table,
            "bounded_context": bounded_context,
        }
        # Add optional fields if provided
        if dev is not None:
            context["dev"] = dev
        if task_id is not None:
            context["task_id"] = task_id
        if schema_file:
            context["schema_file"] = schema_file

        session_id = orchestrator.initialize_run(
            profile=profile,
            providers=providers,
            context=context,
            metadata=metadata,
            standards_provider=effective_standards_provider,
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
@click.option("--events", is_flag=True, help="Emit workflow events to stderr.")
@click.pass_context
def step_cmd(ctx: click.Context, session_id: str, events: bool) -> None:
    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore
        from aiwf.domain.events.emitter import WorkflowEventEmitter

        event_emitter = WorkflowEventEmitter()
        if events:
            from aiwf.domain.events.stderr_observer import StderrEventObserver
            event_emitter.subscribe(StderrEventObserver())

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
            event_emitter=event_emitter,
        )

        state = orchestrator.step(session_id)
        _emit_progress(state)

        phase = state.phase.name
        status = state.status.name
        iteration = getattr(state, "current_iteration", None)

        awaiting, paths = _awaiting_paths_for_state(session_id, state)

        exit_code = 0
        if state.status == WorkflowStatus.CANCELLED:
            exit_code = 3
        elif awaiting:
            exit_code = 2

        last_error = state.last_error

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
                    last_error=last_error,
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

        if last_error:
            click.echo(f"error: {last_error}")

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

        last_error = state.last_error

        if _get_json_mode(ctx):
            _json_emit(
                StatusOutput(
                    exit_code=0,
                    session_id=session_id,
                    phase=phase,
                    status=status,
                    iteration=iteration,
                    session_path=session_path,
                    last_error=last_error,
                )
            )
            raise click.exceptions.Exit(0)

        click.echo(f"phase={phase}")
        click.echo(f"status={status}")
        click.echo(f"iteration={iteration}")
        click.echo(f"session_path={session_path}")
        if last_error:
            click.echo(f"last_error={last_error}")

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
@click.option("--events", is_flag=True, help="Emit workflow events to stderr.")
@click.pass_context
def approve_cmd(ctx: click.Context, session_id: str, hash_prompts: bool, no_hash_prompts: bool, events: bool) -> None:
    try:
        from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
        from aiwf.domain.persistence.session_store import SessionStore
        from aiwf.domain.events.emitter import WorkflowEventEmitter

        cfg = load_config(project_root=Path.cwd(), user_home=Path.home())

        # Determine effective hash_prompts
        effective_hash = cfg.get("hash_prompts", False)
        if hash_prompts:
            effective_hash = True
        elif no_hash_prompts:
            effective_hash = False

        event_emitter = WorkflowEventEmitter()
        if events:
            from aiwf.domain.events.stderr_observer import StderrEventObserver
            event_emitter.subscribe(StderrEventObserver())

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        orchestrator = WorkflowOrchestrator(
            session_store=session_store,
            sessions_root=DEFAULT_SESSIONS_ROOT,
            event_emitter=event_emitter,
        )

        # Call orchestrator.approve
        state = orchestrator.approve(session_id, hash_prompts=effective_hash)
        _emit_progress(state)

        # Collect hashes for output
        hashes: dict[str, str] = {}
        if state.plan_hash:
            hashes["plan.md"] = state.plan_hash
        if state.review_hash:
            hashes["review-response.md"] = state.review_hash
        hashes.update(state.prompt_hashes)
        for artifact in state.artifacts:
            if artifact.sha256:
                hashes[artifact.path] = artifact.sha256

        # Determine approval status
        approved = (
            state.plan_approved
            or state.review_approved
            or any(a.sha256 is not None for a in state.artifacts)
        )

        if state.status == WorkflowStatus.ERROR:
            if _get_json_mode(ctx):
                _json_emit(
                    ApproveOutput(
                        exit_code=1,
                        session_id=session_id,
                        phase=state.phase.name,
                        status=state.status.name,
                        approved=False,
                        hashes=hashes,
                        error=state.last_error,
                    )
                )
            raise click.exceptions.Exit(1)

        if _get_json_mode(ctx):
            _json_emit(
                ApproveOutput(
                    exit_code=0,
                    session_id=session_id,
                    phase=state.phase.name,
                    status=state.status.name,
                    approved=approved,
                    hashes=hashes,
                )
            )
            raise click.exceptions.Exit(0)

        # Plain text output
        click.echo(f"phase={state.phase.name}")
        click.echo(f"status={state.status.name}")
        click.echo(f"approved={approved}")

    except click.exceptions.Exit:
        raise
    except Exception as e:
        error_msg = _format_error(e)
        if _get_json_mode(ctx):
            _json_emit(
                ApproveOutput(
                    exit_code=1,
                    session_id=session_id,
                    phase="",
                    status="",
                    approved=False,
                    error=error_msg,
                )
            )
            raise click.exceptions.Exit(1)
        click.echo(f"Cannot approve: {error_msg}", err=True)
        raise click.exceptions.Exit(1)


@cli.command("list")
@click.option("--status", "filter_status", type=str, default="all", help="Filter by status")
@click.option("--profile", "filter_profile", type=str, default=None, help="Filter by profile")
@click.option("--limit", type=int, default=50, help="Maximum sessions to return")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    filter_status: str,
    filter_profile: str | None,
    limit: int,
) -> None:
    """List all workflow sessions."""
    try:
        from aiwf.domain.persistence.session_store import SessionStore

        session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)
        session_ids = session_store.list_sessions()

        sessions: list[SessionSummary] = []
        for session_id in session_ids:
            try:
                state = session_store.load(session_id)

                # Apply filters
                if filter_status != "all":
                    if filter_status == "in_progress" and state.status != WorkflowStatus.IN_PROGRESS:
                        continue
                    elif filter_status == "complete" and state.phase != WorkflowPhase.COMPLETE:
                        continue
                    elif filter_status == "error" and state.status != WorkflowStatus.ERROR:
                        continue
                    elif filter_status == "cancelled" and state.status != WorkflowStatus.CANCELLED:
                        continue

                if filter_profile and state.profile != filter_profile:
                    continue

                sessions.append(SessionSummary(
                    session_id=state.session_id,
                    profile=state.profile,
                    context=state.context,
                    phase=state.phase.name,
                    status=state.status.name,
                    iteration=state.current_iteration,
                    created_at=state.created_at.isoformat(),
                    updated_at=state.updated_at.isoformat(),
                ))

                if len(sessions) >= limit:
                    break
            except Exception:
                # Skip sessions that fail to load
                continue

        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)

        if _get_json_mode(ctx):
            _json_emit(
                ListOutput(
                    exit_code=0,
                    sessions=sessions,
                    total=len(sessions),
                )
            )
            raise click.exceptions.Exit(0)

        # Plain text table output
        if not sessions:
            click.echo("No sessions found.")
        else:
            # Header
            click.echo(f"{'SESSION_ID':<34}{'PROFILE':<10}{'ENTITY':<10}{'PHASE':<12}{'STATUS':<12}{'UPDATED'}")
            for s in sessions:
                entity = s.context.get("entity", "") if s.context else ""
                click.echo(f"{s.session_id:<34}{s.profile:<10}{entity:<10}{s.phase:<12}{s.status:<12}{s.updated_at}")

    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                ListOutput(
                    exit_code=1,
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e


@cli.command("profiles")
@click.argument("profile_name", type=str, required=False)
@click.pass_context
def profiles_cmd(ctx: click.Context, profile_name: str | None) -> None:
    """List available workflow profiles or show details for a specific profile."""
    try:
        # Import profiles to ensure registration
        import profiles.jpa_mt  # noqa: F401
        from aiwf.domain.profiles.profile_factory import ProfileFactory

        if profile_name:
            # Single profile detail view
            metadata = ProfileFactory.get_metadata(profile_name)
            if metadata is None:
                available = ", ".join(ProfileFactory.list_profiles())
                error_msg = f"Profile '{profile_name}' not found. Available: {available}"
                if _get_json_mode(ctx):
                    _json_emit(
                        ProfilesOutput(
                            exit_code=1,
                            error=error_msg,
                        )
                    )
                    raise click.exceptions.Exit(1)
                raise click.ClickException(error_msg)

            profile_detail = ProfileDetail(
                name=metadata["name"],
                description=metadata["description"],
                target_stack=metadata.get("target_stack", "Unknown"),
                scopes=metadata.get("scopes", []),
                phases=metadata.get("phases", []),
                requires_config=metadata.get("requires_config", False),
                config_keys=metadata.get("config_keys", []),
            )

            if _get_json_mode(ctx):
                _json_emit(
                    ProfilesOutput(
                        exit_code=0,
                        profile=profile_detail,
                    )
                )
                raise click.exceptions.Exit(0)

            # Plain text single profile
            click.echo(f"Profile: {profile_detail.name}")
            click.echo(f"Description: {profile_detail.description}")
            click.echo(f"Target Stack: {profile_detail.target_stack}")
            click.echo(f"Scopes: {', '.join(profile_detail.scopes)}")
            click.echo(f"Phases: {', '.join(profile_detail.phases)}")
            requires_str = "yes" if profile_detail.requires_config else "no"
            click.echo(f"Requires Config: {requires_str}")
            if profile_detail.config_keys:
                click.echo(f"Config Keys: {', '.join(profile_detail.config_keys)}")

        else:
            # List all profiles
            all_metadata = ProfileFactory.get_all_metadata()
            profiles_list = [
                ProfileSummary(
                    name=m["name"],
                    description=m["description"],
                    scopes=m.get("scopes", []),
                    requires_config=m.get("requires_config", False),
                )
                for m in all_metadata
            ]

            if _get_json_mode(ctx):
                _json_emit(
                    ProfilesOutput(
                        exit_code=0,
                        profiles=profiles_list,
                    )
                )
                raise click.exceptions.Exit(0)

            # Plain text table output
            if not profiles_list:
                click.echo("No profiles registered.")
            else:
                click.echo(f"{'PROFILE':<10}{'DESCRIPTION':<45}{'SCOPES'}")
                for p in profiles_list:
                    scopes_str = ", ".join(p.scopes)
                    click.echo(f"{p.name:<10}{p.description:<45}{scopes_str}")

    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                ProfilesOutput(
                    exit_code=1,
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e


@cli.command("providers")
@click.argument("provider_name", type=str, required=False)
@click.pass_context
def providers_cmd(ctx: click.Context, provider_name: str | None) -> None:
    """List available AI providers or show details for a specific provider."""
    try:
        # Import providers to ensure registration
        from aiwf.domain.providers import ProviderFactory  # noqa: F401

        if provider_name:
            # Single provider detail view
            metadata = ProviderFactory.get_metadata(provider_name)
            if metadata is None:
                available = ", ".join(ProviderFactory.list_providers())
                error_msg = f"Provider '{provider_name}' not found. Available: {available}"
                if _get_json_mode(ctx):
                    _json_emit(
                        ProvidersOutput(
                            exit_code=1,
                            error=error_msg,
                        )
                    )
                    raise click.exceptions.Exit(1)
                raise click.ClickException(error_msg)

            provider_detail = ProviderDetail(
                name=metadata["name"],
                description=metadata["description"],
                requires_config=metadata.get("requires_config", False),
                config_keys=metadata.get("config_keys", []),
            )

            if _get_json_mode(ctx):
                _json_emit(
                    ProvidersOutput(
                        exit_code=0,
                        provider=provider_detail,
                    )
                )
                raise click.exceptions.Exit(0)

            # Plain text single provider
            click.echo(f"Provider: {provider_detail.name}")
            click.echo(f"Description: {provider_detail.description}")
            requires_str = "yes" if provider_detail.requires_config else "no"
            click.echo(f"Requires Config: {requires_str}")

        else:
            # List all providers
            all_metadata = ProviderFactory.get_all_metadata()
            providers_list = [
                ProviderSummary(
                    name=m["name"],
                    description=m["description"],
                    requires_config=m.get("requires_config", False),
                )
                for m in all_metadata
            ]

            if _get_json_mode(ctx):
                _json_emit(
                    ProvidersOutput(
                        exit_code=0,
                        providers=providers_list,
                    )
                )
                raise click.exceptions.Exit(0)

            # Plain text table output
            if not providers_list:
                click.echo("No providers registered.")
            else:
                click.echo(f"{'PROVIDER':<10}{'DESCRIPTION':<45}{'CONFIG'}")
                for p in providers_list:
                    config_str = "required" if p.requires_config else "none"
                    click.echo(f"{p.name:<10}{p.description:<45}{config_str}")

    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                ProvidersOutput(
                    exit_code=1,
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e


def _validate_ai_provider(key: str) -> list[ValidationResult]:
    """Validate a single AI provider."""
    from aiwf.domain.providers.provider_factory import ProviderFactory
    from aiwf.domain.errors import ProviderError

    try:
        provider = ProviderFactory.create(key)
        provider.validate()
        return [ValidationResult(provider_type="ai", provider_key=key, passed=True)]
    except ProviderError as e:
        return [
            ValidationResult(
                provider_type="ai", provider_key=key, passed=False, error=str(e)
            )
        ]
    except KeyError:
        return [
            ValidationResult(
                provider_type="ai", provider_key=key, passed=False, error="Not registered"
            )
        ]


def _validate_standards_provider(
    key: str, profile_key: str | None
) -> list[ValidationResult]:
    """Validate a single standards provider.

    Standards providers require config from a profile. If no profile is specified,
    uses the project's configured profile from load_config().

    Errors:
        - Profile is required but not specified
        - Profile specified but not registered
        - Profile fails to load
        - Standards provider not registered
        - Standards provider validation fails
    """
    from aiwf.domain.standards import StandardsProviderFactory
    from aiwf.domain.profiles.profile_factory import ProfileFactory
    from aiwf.domain.errors import ProviderError

    try:
        # Determine which profile to use
        cfg = load_config(project_root=Path.cwd(), user_home=Path.home())
        profile_to_use = profile_key or cfg.get("profile")

        # Profile is required
        if not profile_to_use:
            return [
                ValidationResult(
                    provider_type="standards",
                    provider_key=key,
                    passed=False,
                    error="Profile is required. Specify --profile or set 'profile' in config.",
                )
            ]

        # Check if profile is registered
        if not ProfileFactory.is_registered(profile_to_use):
            return [
                ValidationResult(
                    provider_type="standards",
                    provider_key=key,
                    passed=False,
                    error=f"Profile not registered: {profile_to_use}",
                )
            ]

        # Try to create the profile
        try:
            profile_instance = ProfileFactory.create(profile_to_use)
        except Exception as e:
            return [
                ValidationResult(
                    provider_type="standards",
                    provider_key=key,
                    passed=False,
                    error=f"Failed to load profile '{profile_to_use}': {e}",
                )
            ]

        standards_config = profile_instance.get_standards_config()

        provider = StandardsProviderFactory.create(key, standards_config)
        provider.validate()
        return [
            ValidationResult(provider_type="standards", provider_key=key, passed=True)
        ]
    except ProviderError as e:
        return [
            ValidationResult(
                provider_type="standards", provider_key=key, passed=False, error=str(e)
            )
        ]
    except KeyError as e:
        return [
            ValidationResult(
                provider_type="standards",
                provider_key=key,
                passed=False,
                error=f"Standards provider not registered: {e}",
            )
        ]
    except Exception as e:
        return [
            ValidationResult(
                provider_type="standards", provider_key=key, passed=False, error=str(e)
            )
        ]


@cli.command("validate")
@click.argument("provider_type", type=click.Choice(["ai", "standards", "all"]))
@click.argument("provider_key", required=False)
@click.option(
    "--profile",
    "profile_key",
    required=False,
    type=str,
    help="Profile to use for standards provider config (defaults to project config)",
)
@click.pass_context
def validate_cmd(
    ctx: click.Context,
    provider_type: str,
    provider_key: str | None,
    profile_key: str | None,
) -> None:
    """Validate provider configuration.

    Examples:
        aiwf validate ai manual
        aiwf validate standards scoped-layer-fs
        aiwf validate ai  # validates all AI providers
        aiwf validate all  # validates everything
    """
    try:
        # Import to ensure registration
        from aiwf.domain.providers import ProviderFactory
        from aiwf.domain.standards import StandardsProviderFactory
        import profiles.jpa_mt  # noqa: F401

        results: list[ValidationResult] = []

        if provider_type in ("ai", "all"):
            if provider_key and provider_type == "ai":
                # Validate specific AI provider
                results.extend(_validate_ai_provider(provider_key))
            else:
                # Validate all AI providers
                for key in ProviderFactory.list_providers():
                    results.extend(_validate_ai_provider(key))

        if provider_type in ("standards", "all"):
            if provider_key and provider_type == "standards":
                # Validate specific standards provider
                results.extend(_validate_standards_provider(provider_key, profile_key))
            else:
                # Validate all standards providers
                for key in StandardsProviderFactory.list_providers():
                    results.extend(_validate_standards_provider(key, profile_key))

        all_passed = all(r.passed for r in results)
        exit_code = 0 if all_passed else 1

        if _get_json_mode(ctx):
            _json_emit(
                ValidateOutput(
                    exit_code=exit_code,
                    results=results,
                    all_passed=all_passed,
                )
            )
            raise click.exceptions.Exit(exit_code)

        # Plain text output
        for r in results:
            status = "OK" if r.passed else "FAILED"
            click.echo(f"  {r.provider_type}:{r.provider_key}: {status}")
            if r.error:
                click.echo(f"    {r.error}")

        passed = sum(1 for r in results if r.passed)
        click.echo(f"\n{passed} of {len(results)} providers ready.")

        if not all_passed:
            raise click.exceptions.Exit(1)

    except click.exceptions.Exit:
        raise
    except Exception as e:
        if _get_json_mode(ctx):
            _json_emit(
                ValidateOutput(
                    exit_code=1,
                    error=str(e),
                )
            )
            raise click.exceptions.Exit(1)
        raise click.ClickException(str(e)) from e


# Discover and register profiles at import time
def _init_profiles():
    from aiwf.interface.cli.profile_discovery import discover_and_register_profiles
    try:
        registered = discover_and_register_profiles(cli)
        logger.debug(f"Registered profiles: {registered}")
    except Exception as e:
        logger.warning(f"Error during profile discovery: {e}")


_init_profiles()

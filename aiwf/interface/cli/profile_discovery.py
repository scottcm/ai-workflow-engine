"""Profile discovery module.

Discovers and registers workflow profiles from:
1. Local directory (configurable via profiles_dir, default ~/.aiwf/profiles/)
2. Entry points (aiwf.profiles group)

Entry points have higher precedence and override local profiles on name collision.
"""
import importlib.util
import logging
import os
from pathlib import Path
from typing import Callable

import click
from importlib.metadata import entry_points

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.profiles.workflow_profile import WorkflowProfile

logger = logging.getLogger(__name__)

RegisterFn = Callable[[click.Group], type[WorkflowProfile]]


def discover_and_register_profiles(
    cli: click.Group,
    profiles_dir: Path | None = None,
) -> dict[str, str]:
    """Discover and register all available profiles.

    Args:
        cli: Click command group to add profile commands to.
        profiles_dir: Directory to scan for local profiles. Defaults to ~/.aiwf/profiles/.

    Returns dict of {profile_name: source} for diagnostics.
    """
    registered = {}

    # 1. Local directory first (lower precedence)
    local_profiles = _discover_local_profiles(cli, profiles_dir=profiles_dir)
    registered.update(local_profiles)

    # 2. Entry points second (higher precedence, overwrites local)
    entrypoint_profiles = _discover_entrypoint_profiles(cli)
    registered.update(entrypoint_profiles)

    return registered


def _discover_local_profiles(
    cli: click.Group,
    profiles_dir: Path | None = None,
) -> dict[str, str]:
    """Discover profiles from local directory."""
    registered = {}

    # Determine profiles directory with precedence:
    # 1. Explicit profiles_dir parameter
    # 2. AIWF_PROFILES_DIR environment variable
    # 3. Default ~/.aiwf/profiles/
    if profiles_dir is not None:
        local_dir = profiles_dir
    elif os.environ.get("AIWF_PROFILES_DIR"):
        local_dir = Path(os.environ["AIWF_PROFILES_DIR"])
    else:
        local_dir = Path.home() / ".aiwf" / "profiles"

    if not local_dir.exists():
        return registered

    for profile_dir in local_dir.iterdir():
        if not profile_dir.is_dir():
            continue

        init_file = profile_dir / "__init__.py"
        if not init_file.exists():
            continue

        profile_name = profile_dir.name

        try:
            # Load module from file
            spec = importlib.util.spec_from_file_location(
                f"aiwf_local_profile_{profile_name}",
                init_file
            )
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for local profile '{profile_name}'")
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "register"):
                logger.warning(f"Local profile '{profile_name}' has no register() function")
                continue

            register_fn: RegisterFn = module.register

            # Create command group with placeholder help
            profile_group = click.Group(name=profile_name)
            profile_class = register_fn(profile_group)

            # Update help text from profile metadata
            metadata = profile_class.get_metadata() if hasattr(profile_class, "get_metadata") else {}
            profile_group.help = metadata.get("description", f"Commands for {profile_name} profile")

            # Add to CLI and factory
            cli.add_command(profile_group)
            ProfileFactory.register(profile_name, profile_class)

            registered[profile_name] = f"local:{profile_dir}"
            logger.debug(f"Loaded local profile: {profile_name}")

        except Exception as e:
            logger.warning(f"Failed to load local profile '{profile_name}': {e}")
            # Continue - don't crash CLI for one bad profile

    return registered


def _discover_entrypoint_profiles(cli: click.Group) -> dict[str, str]:
    """Discover profiles from entry points."""
    registered = {}

    try:
        eps = entry_points(group="aiwf.profiles")
    except TypeError:
        # Python < 3.10 compatibility
        eps = entry_points().get("aiwf.profiles", [])

    for ep in eps:
        profile_name = ep.name

        try:
            register_fn: RegisterFn = ep.load()

            # Create command group with placeholder help
            profile_group = click.Group(name=profile_name)
            profile_class = register_fn(profile_group)

            # Update help text from profile metadata
            metadata = profile_class.get_metadata() if hasattr(profile_class, "get_metadata") else {}
            profile_group.help = metadata.get("description", f"Commands for {profile_name} profile")

            # Log if overwriting local profile
            if profile_name in registered or ProfileFactory.is_registered(profile_name):
                logger.info(f"Entry point profile '{profile_name}' overrides local profile")

            # Add to CLI and factory (overwrites local if exists)
            cli.add_command(profile_group)
            ProfileFactory.register(profile_name, profile_class)

            registered[profile_name] = f"entrypoint:{ep.value}"
            logger.debug(f"Loaded installed profile: {profile_name}")

        except Exception as e:
            logger.warning(f"Failed to load profile '{profile_name}': {e}")

    return registered
# Phase 2: CLI Entry Point Infrastructure - Implementation Guide

**Goal:** Enable profiles to register their own CLI commands via entry points and local directory discovery.

**Dependencies:** None (can run in parallel with Phase 1)

---

## Overview

Create infrastructure for profiles to register commands dynamically:
1. Entry point discovery (`aiwf.profiles` group)
2. Local directory scanning (`~/.aiwf/profiles/`)
3. Unified `register()` pattern returning profile class
4. Graceful handling of profile load failures

---

## Step 1: Define Registration Pattern

**File:** `aiwf/domain/profiles/workflow_profile.py`

Document the expected registration function signature:

```python
# Profile registration function signature:
# def register(cli_group: click.Group) -> type[WorkflowProfile]:
#     """Register commands and return profile class."""
#     @cli_group.command("init")
#     def init(...):
#         ...
#     return MyProfileClass
```

---

## Step 2: Create Profile Discovery Module

**File:** `aiwf/interface/cli/profile_discovery.py` (new)

```python
import importlib.util
import logging
from pathlib import Path
from typing import Callable

import click
from importlib.metadata import entry_points

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.profiles.workflow_profile import WorkflowProfile

logger = logging.getLogger(__name__)

RegisterFn = Callable[[click.Group], type[WorkflowProfile]]


def discover_and_register_profiles(cli: click.Group) -> dict[str, str]:
    """Discover and register all available profiles.

    Returns dict of {profile_name: source} for diagnostics.
    """
    registered = {}

    # 1. Local directory first (lower precedence)
    local_profiles = _discover_local_profiles(cli)
    registered.update(local_profiles)

    # 2. Entry points second (higher precedence, overwrites local)
    entrypoint_profiles = _discover_entrypoint_profiles(cli)
    registered.update(entrypoint_profiles)

    return registered


def _discover_local_profiles(cli: click.Group) -> dict[str, str]:
    """Discover profiles from ~/.aiwf/profiles/ directory."""
    registered = {}
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

            # Create command group and register
            profile_group = click.Group(
                name=profile_name,
                help=f"Commands for {profile_name} profile"
            )
            profile_class = register_fn(profile_group)

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

            # Create command group and register
            profile_group = click.Group(
                name=profile_name,
                help=f"Commands for {profile_name} profile"
            )
            profile_class = register_fn(profile_group)

            # Log if overwriting local profile
            if profile_name in registered:
                logger.info(f"Entry point profile '{profile_name}' overrides local profile")

            # Add to CLI and factory (overwrites local if exists)
            cli.add_command(profile_group)
            ProfileFactory.register(profile_name, profile_class)

            registered[profile_name] = f"entrypoint:{ep.value}"
            logger.debug(f"Loaded installed profile: {profile_name}")

        except Exception as e:
            logger.warning(f"Failed to load profile '{profile_name}': {e}")

    return registered
```

---

## Step 3: Update Main CLI

**File:** `aiwf/interface/cli/cli.py`

Import and call discovery at module load time:

```python
import click
import logging

logger = logging.getLogger(__name__)

@click.group()
@click.option("--json", is_flag=True, help="Output JSON")
@click.pass_context
def cli(ctx, json):
    ctx.ensure_object(dict)
    ctx.obj["json"] = json

# Core commands
# ... step, approve, status, list, profiles, providers, validate ...

# Discover and register profiles at import time
def _init_profiles():
    from aiwf.interface.cli.profile_discovery import discover_and_register_profiles
    try:
        registered = discover_and_register_profiles(cli)
        logger.debug(f"Registered profiles: {registered}")
    except Exception as e:
        logger.warning(f"Error during profile discovery: {e}")

_init_profiles()
```

---

## Step 4: Update ProfileFactory

**File:** `aiwf/domain/profiles/profile_factory.py`

Ensure register() method exists and is idempotent:

```python
class ProfileFactory:
    _registry: dict[str, type[WorkflowProfile]] = {}

    @classmethod
    def register(cls, name: str, profile_class: type[WorkflowProfile]) -> None:
        """Register a profile class. Overwrites if already registered."""
        cls._registry[name] = profile_class

    @classmethod
    def get(cls, name: str) -> type[WorkflowProfile] | None:
        """Get a registered profile class by name."""
        return cls._registry.get(name)

    @classmethod
    def list_profiles(cls) -> list[str]:
        """List all registered profile names."""
        return list(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear registry (for testing)."""
        cls._registry.clear()
```

---

## Step 5: Add Profiles Command Enhancement

**File:** `aiwf/interface/cli/cli.py`

Enhance `profiles` command to show source:

```python
@cli.command("profiles")
@pass_json_context
def profiles(json_mode):
    """List available workflow profiles."""
    from aiwf.domain.profiles.profile_factory import ProfileFactory

    profiles_list = []
    for name in ProfileFactory.list_profiles():
        profile_class = ProfileFactory.get(name)
        if profile_class:
            metadata = profile_class.get_metadata()
            profiles_list.append({
                "name": name,
                "description": metadata.get("description", ""),
                "phases": metadata.get("phases", []),
            })

    if json_mode:
        output_json(ProfilesOutput(profiles=profiles_list))
    else:
        if not profiles_list:
            click.echo("No profiles registered.")
            click.echo("")
            click.echo("Install a profile package or create one in ~/.aiwf/profiles/")
        else:
            for p in profiles_list:
                click.echo(f"{p['name']}: {p['description']}")
```

---

## Step 6: Update pyproject.toml

**File:** `pyproject.toml`

Add entry point for jpa-mt profile:

```toml
[project.entry-points."aiwf.profiles"]
jpa-mt = "profiles.jpa_mt:register"
```

---

## Step 7: Create jpa-mt Register Function (Stub)

**File:** `profiles/jpa_mt/__init__.py`

Create stub register function (full implementation in Phase 4):

```python
import click
from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile


def register(cli_group: click.Group) -> type:
    """Register jpa-mt commands and return profile class.

    Full implementation in Phase 4. This stub allows discovery to work.
    """
    # Stub - commands will be added in Phase 4
    @cli_group.command("info")
    def info():
        """Show jpa-mt profile information."""
        click.echo("JPA Multi-Tenant Profile")
        click.echo("Use 'aiwf jpa-mt init' to start a new session.")

    return JpaMtProfile
```

---

## Testing Requirements

**File:** `tests/unit/interface/cli/test_profile_discovery.py` (new)

1. Test local profile discovery finds profiles in ~/.aiwf/profiles/
2. Test entry point discovery finds installed profiles
3. Test entry points override local profiles on name collision (entry point wins)
4. Test name collision logs a warning for discoverability
5. Test failed profile load doesn't crash CLI
6. Test profile without register() function is skipped
7. Test ProfileFactory.register() works correctly
8. Test ProfileFactory.list_profiles() returns registered profiles

**File:** `tests/integration/test_cli.py`

8. Test `aiwf --help` shows profile command groups
9. Test `aiwf profiles` lists discovered profiles
10. Test `aiwf <profile> --help` shows profile commands

---

## Local Profile Structure

Document expected structure for local profiles:

```
~/.aiwf/profiles/
└── my-profile/
    ├── __init__.py          # Must define register(group) -> ProfileClass
    ├── my_profile.py        # WorkflowProfile implementation
    └── templates/           # Profile templates (optional)
```

Example `__init__.py`:

```python
import click
from .my_profile import MyProfile

def register(cli_group: click.Group) -> type:
    @cli_group.command("init")
    @click.option("--name", required=True)
    def init(name):
        """Initialize my-profile session."""
        click.echo(f"Creating session with name: {name}")
        # ... create session ...

    return MyProfile
```

---

## Files Changed

| File | Change |
|------|--------|
| `aiwf/interface/cli/profile_discovery.py` | New module |
| `aiwf/interface/cli/cli.py` | Call discovery, enhance profiles command |
| `aiwf/domain/profiles/profile_factory.py` | Ensure register/list methods |
| `profiles/jpa_mt/__init__.py` | Add register() stub |
| `pyproject.toml` | Add entry point |
| `tests/unit/interface/cli/test_profile_discovery.py` | New tests |

---

## Acceptance Criteria

- [ ] Profiles discovered from entry points
- [ ] Profiles discovered from ~/.aiwf/profiles/
- [ ] Entry points override local on name collision
- [ ] Failed profile loads logged but don't crash CLI
- [ ] `aiwf --help` shows profile command groups
- [ ] `aiwf profiles` lists all discovered profiles
- [ ] ProfileFactory populated by discovery
- [ ] All tests pass